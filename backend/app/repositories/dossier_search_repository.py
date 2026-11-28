"""Recherche plein texte à travers les dossiers (issue #642).

Un dossier est trouvé quand **chaque** mot cherché apparaît quelque part chez lui : nom, nom d'un document, valeur
extraite retenue ou texte d'une page (les mots peuvent être répartis). Une règle de sécurité, appliquée à **chaque**
source : seulement les dossiers visibles de la personne (`visible_clause`), dans la requête elle-même.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, extract, func, literal, literal_column, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.security.factory import RequestContext
from app.models.analyse import Analyse
from app.models.analyse_theme import AnalyseTheme
from app.models.document_page import DocumentPage, PredictionValidationStatus
from app.models.dossier import Dossier, DossierDocument
from app.models.dossier_analysis import AnalysisElement, AnalysisElementKind, AnalysisElementVersion, DossierAnalysis
from app.repositories.dossier_event_repository import DossierEventRepository
from app.schemas.dossier_search import DossierSearchOut, FoundDossierOut, SearchExcerptOut, SearchSegmentOut
from app.services.dossier_access import visible_clause
from app.services.full_text import any_term, headline, search_terms, split_headline, term_query, vector

MAX_EXCERPTS = 3
# Poids d'un mot selon l'endroit le plus parlant où il est trouvé.
_NAME, _VALUE, _DOCUMENT, _PAGE = 8, 4, 2, 1
_REFERENCE = re.compile(r"\bDOS-(\d{4})-(\d{1,15})\b", re.IGNORECASE)
_SEARCHED_KINDS = (AnalysisElementKind.CLASSIFICATION, AnalysisElementKind.ENTITY, AnalysisElementKind.FIELD)
_SEPARATORS, _SPACES = literal_column("'_.-/'"), literal_column("'    '")


# Ces expressions doivent rester identiques à celles des index (migration « recherche à travers les dossiers »).
def _name_text(column: ColumnElement[str]) -> ColumnElement[str]:
    # « justificatif_domicile.pdf » serait sinon un seul mot.
    return func.translate(column, _SEPARATORS, _SPACES)


def _value_text() -> ColumnElement[str]:
    value = AnalysisElementVersion.value
    return func.coalesce(value.op("->>")(literal_column("'value'")), value.op("->>")(literal_column("'label'")))


def _page_vector() -> ColumnElement[Any]:
    return DocumentPage.search_vector


def _once(tsquery: ColumnElement[Any]) -> ColumnElement[Any]:
    # `to_tsquery` serait sinon rejoué à chaque ligne comparée : en sous-requête, il n'est calculé qu'une fois.
    return select(tsquery).scalar_subquery()


def _retained_values(*columns: Any) -> Select:
    """Les valeurs retenues de l'analyse courante de chaque dossier (une valeur rejetée ne compte pas)."""
    latest = aliased(DossierAnalysis)
    return (
        select(*columns)
        .select_from(AnalysisElementVersion)
        .join(AnalysisElement, AnalysisElement.retained_version_id == AnalysisElementVersion.id)
        .join(DossierAnalysis, DossierAnalysis.id == AnalysisElement.analysis_id)
        .join(Dossier, Dossier.id == DossierAnalysis.dossier_id)
        .where(
            AnalysisElement.kind.in_(_SEARCHED_KINDS),
            AnalysisElementVersion.validation_status.is_distinct_from(PredictionValidationStatus.REJECTED.value),
            DossierAnalysis.sequence
            == select(func.max(latest.sequence)).where(latest.dossier_id == Dossier.id).scalar_subquery(),
        )
    )


def _pages(*columns: Any) -> Select:
    return (
        select(*columns)
        .select_from(DocumentPage)
        .join(DossierDocument, DossierDocument.id == DocumentPage.dossier_document_id)
        .join(Dossier, Dossier.id == DossierDocument.dossier_id)
    )


def _documents(*columns: Any) -> Select:
    return select(*columns).select_from(DossierDocument).join(Dossier, Dossier.id == DossierDocument.dossier_id)


def split_reference(query: str) -> tuple[tuple[int, int] | None, str]:
    """Sépare une référence de dossier (« DOS-2026-0012 ») des mots à chercher."""
    found = _REFERENCE.search(query)
    if found is None:
        return None, query
    return (int(found[1]), int(found[2])), _REFERENCE.sub(" ", query)


def _reference_clause(reference: tuple[int, int]) -> ColumnElement[bool]:
    year, number = reference
    created = func.timezone("UTC", Dossier.created_at)
    return and_(Dossier.ref_number == number, extract("year", created) == year)


def _segments(value: str) -> list[SearchSegmentOut]:
    return [SearchSegmentOut(text=text, highlighted=highlighted) for text, highlighted in split_headline(value)]


class DossierSearchRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, *, user: RequestContext, query: str, limit: int) -> DossierSearchOut:
        reference, words = split_reference(query)
        terms = search_terms(words)
        if reference is None and not terms:
            return DossierSearchOut(dossiers=[], total=0)

        ids, total = await self._ranked(user, terms, reference, limit)
        if not ids:
            return DossierSearchOut(dossiers=[], total=total)
        excerpts = await self._excerpts(ids, terms)
        await self._trace_admin_access(user, [dossier_id for dossier_id in ids if excerpts.get(dossier_id)])
        return DossierSearchOut(dossiers=await self._describe(ids, excerpts), total=total)

    async def _ranked(
        self, user: RequestContext, terms: list[str], reference: tuple[int, int] | None, limit: int
    ) -> tuple[list[uuid.UUID], int]:
        """Les dossiers les plus pertinents et le nombre total trouvé, en une requête."""
        visible = [visible_clause(user)]
        if reference is not None:
            visible.append(_reference_clause(reference))

        if not terms:
            found = select(Dossier.id, literal(0).label("score")).where(*visible).subquery()
        else:
            queries = [_once(term_query(term)) for term in terms]
            sources = (
                (lambda *c: select(*c).select_from(Dossier), vector(_name_text(Dossier.name)), _NAME),
                (_retained_values, vector(_value_text()), _VALUE),
                (_documents, vector(_name_text(DossierDocument.name)), _DOCUMENT),
                (_pages, _page_vector(), _PAGE),
            )
            # Une branche par source et par mot, qui passe par l'index. Comparer chaque ligne à chaque mot en une seule
            # passe relit le vecteur autant de fois : dix fois plus lent sur un mot courant.
            hits = union_all(
                *[
                    statement_of(
                        Dossier.id.label("id"), literal(i).label("term"), literal(weight).label("weight")
                    ).where(*visible, document.op("@@")(query))
                    for statement_of, document, weight in sources
                    for i, query in enumerate(queries)
                ]
            ).subquery()
            per_term = (
                select(hits.c.id, func.max(hits.c.weight).label("weight"), func.count().label("hits"))
                .group_by(hits.c.id, hits.c.term)
                .subquery()
            )
            # Le meilleur endroit de chaque mot d'abord, puis le nombre d'occurrences pour départager.
            score = func.sum(per_term.c.weight) * 100 + func.least(func.sum(per_term.c.hits), 99)
            found = (
                select(per_term.c.id, score.label("score"))
                .group_by(per_term.c.id)
                .having(func.count() == len(terms))
                .subquery()
            )

        rows = (
            await self.db.execute(
                select(found.c.id, func.count().over().label("total"))
                .join(Dossier, Dossier.id == found.c.id)
                .order_by(found.c.score.desc(), Dossier.created_at.desc(), Dossier.id)
                .limit(limit)
            )
        ).all()
        return [row.id for row in rows], rows[0].total if rows else 0

    async def _excerpts(self, ids: list[uuid.UUID], terms: list[str]) -> dict[uuid.UUID, list[SearchExcerptOut]]:
        """Les meilleurs extraits des seuls dossiers affichés : pages, puis valeurs extraites, puis documents."""
        if not terms:
            return {}
        wanted = _once(any_term(terms))
        excerpts: dict[uuid.UUID, list[SearchExcerptOut]] = {}

        def add(dossier_id: uuid.UUID, excerpt: SearchExcerptOut) -> None:
            kept = excerpts.setdefault(dossier_id, [])
            if len(kept) < MAX_EXCERPTS:
                kept.append(excerpt)

        def best(statement: Select, document: ColumnElement[Any], *order: ColumnElement[Any]) -> Any:
            rank = (
                func.row_number()
                .over(partition_by=Dossier.id, order_by=(func.ts_rank(document, wanted).desc(), *order))
                .label("rank")
            )
            return statement.add_columns(rank).where(Dossier.id.in_(ids), document.op("@@")(wanted)).subquery()

        pages = best(
            _pages(
                Dossier.id.label("dossier_id"),
                DocumentPage.id.label("page_id"),
                DocumentPage.page_number,
                DossierDocument.id.label("document_id"),
                DossierDocument.name.label("document_name"),
            ),
            _page_vector(),
            DocumentPage.page_number,
            DocumentPage.id,
        )
        rows = await self.db.execute(
            select(pages, headline(DocumentPage.content, wanted).label("excerpt"))
            .join(DocumentPage, DocumentPage.id == pages.c.page_id)
            .where(pages.c.rank <= MAX_EXCERPTS)
            .order_by(pages.c.dossier_id, pages.c.rank)
        )
        for row in rows:
            add(
                row.dossier_id,
                SearchExcerptOut(
                    document_id=row.document_id,
                    document_name=row.document_name,
                    page=row.page_number,
                    segments=_segments(row.excerpt),
                ),
            )

        values = best(
            _retained_values(
                Dossier.id.label("dossier_id"),
                AnalysisElement.document_id,
                AnalysisElement.first_page_number,
                AnalysisElement.definition_name,
                _value_text().label("value"),
            ),
            vector(_value_text()),
            AnalysisElement.id,
        )
        rows = await self.db.execute(
            select(
                values, DossierDocument.name.label("document_name"), headline(values.c.value, wanted).label("excerpt")
            )
            .outerjoin(DossierDocument, DossierDocument.id == values.c.document_id)
            .where(values.c.rank <= MAX_EXCERPTS)
            .order_by(values.c.dossier_id, values.c.rank)
        )
        for row in rows:
            add(
                row.dossier_id,
                SearchExcerptOut(
                    document_id=row.document_id,
                    document_name=row.document_name,
                    page=row.first_page_number,
                    field=row.definition_name,
                    segments=_segments(row.excerpt),
                ),
            )

        documents = best(
            _documents(
                Dossier.id.label("dossier_id"),
                DossierDocument.id.label("document_id"),
                DossierDocument.name.label("document_name"),
            ),
            vector(_name_text(DossierDocument.name)),
            DossierDocument.id,
        )
        rows = await self.db.execute(
            select(documents, headline(_name_text(documents.c.document_name), wanted).label("excerpt"))
            .where(documents.c.rank <= MAX_EXCERPTS)
            .order_by(documents.c.dossier_id, documents.c.rank)
        )
        for row in rows:
            # Un document déjà cité par une page ou une valeur n'apporte rien de plus.
            if any(e.document_id == row.document_id for e in excerpts.get(row.dossier_id, [])):
                continue
            add(
                row.dossier_id,
                SearchExcerptOut(
                    document_id=row.document_id, document_name=row.document_name, segments=_segments(row.excerpt)
                ),
            )
        return excerpts

    async def _trace_admin_access(self, user: RequestContext, shown: Sequence[uuid.UUID]) -> None:
        """Un administrateur qui lit un extrait d'un dossier hors de ses groupes est tracé (#182)."""
        if not user.is_admin or not shown:
            return
        as_member = visible_clause(replace(user, is_admin=False))
        own = set(await self.db.scalars(select(Dossier.id).where(Dossier.id.in_(shown), as_member)))
        events = DossierEventRepository(self.db)
        for dossier_id in shown:
            if dossier_id not in own:
                await events.record_admin_access(dossier_id, user, "POST", write=False)

    async def _describe(
        self, ids: list[uuid.UUID], excerpts: dict[uuid.UUID, list[SearchExcerptOut]]
    ) -> list[FoundDossierOut]:
        rows = await self.db.execute(
            select(Dossier, Analyse.name, AnalyseTheme.name)
            .outerjoin(Analyse, Analyse.id == Dossier.analyse_id)
            .outerjoin(AnalyseTheme, AnalyseTheme.id == Analyse.theme_id)
            .where(Dossier.id.in_(ids))
        )
        found = {
            dossier.id: FoundDossierOut(
                id=dossier.id,
                reference=dossier.reference,
                name=dossier.name,
                analyse_name=analyse_name,
                theme_name=theme_name,
                excerpts=excerpts.get(dossier.id, []),
            )
            for dossier, analyse_name, theme_name in rows.unique()
        }
        return [found[dossier_id] for dossier_id in ids if dossier_id in found]
