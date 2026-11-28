"""Les points communs entre des dossiers (issue #643) : mêmes valeurs extraites, mêmes fichiers.

Tout est calculé à la lecture, sur les seuls dossiers visibles de la personne (`visible_clause`) : un point commun ne
mentionne jamais un dossier absent de la liste demandée.

- Valeurs : la valeur retenue d'une entité ou d'un champ, comparée sans tenir compte de la casse, des accents ni des
  espaces. Les dates, les nombres et les booléens ne relient pas.
- Fichiers : même empreinte de contenu.
- Ce que partagent trop de dossiers visibles (mention type, formulaire vierge) est écarté : cela relierait tout.
"""

import hashlib
import uuid
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, distinct, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.analyse import Analyse, EntityDefinition, EntityType
from app.models.dossier import Dossier, DossierDocument
from app.models.dossier_analysis import AnalysisElement, AnalysisElementKind, AnalysisElementVersion
from app.schemas.dossier_search import LinkOccurrenceOut, SharedItemOut
from app.services.dossier_access import visible_clause
from app.services.retained_values import retained_values, value_text

LINKED_KINDS = (AnalysisElementKind.ENTITY, AnalysisElementKind.FIELD)
_UNLINKED_TYPES = (EntityType.DATE, EntityType.NOMBRE, EntityType.BOOLEEN)
_EMPTY_VALUES = ("oui", "non", "neant", "aucun", "aucune", "inconnu", "inconnue", "n/a", "sans objet")
MIN_LENGTH, MAX_LENGTH = 3, 200
# Un point commun est « trop fréquent » au-delà de ce nombre de dossiers visibles, ou de cette part d'entre eux.
COMMON_FLOOR, COMMON_SHARE = 20, 0.1
MAX_ITEMS = 40
MAX_OCCURRENCES_PER_DOSSIER = 3


def normalized_value() -> ColumnElement[str]:
    """La clé de comparaison d'une valeur. Identique à l'expression de l'index `ix_analysis_element_versions_link`."""
    return func.dossier_link_key(func.left(value_text(), literal_column("300")))


def _linkable(*columns: Any) -> Select:
    """Les valeurs retenues des types qui peuvent relier deux dossiers."""
    # Aucun filtre sur la clé ici : il la ferait calculer pour toutes les valeurs de la base (`_is_meaningful`).
    return (
        retained_values(LINKED_KINDS, *columns)
        .outerjoin(EntityDefinition, EntityDefinition.id == AnalysisElement.definition_id)
        # Une définition supprimée depuis ne dit plus son type : la valeur relie encore.
        .where(or_(EntityDefinition.type.is_(None), EntityDefinition.type.not_in(_UNLINKED_TYPES)))
    )


def _is_meaningful(key: str | None) -> bool:
    return key is not None and MIN_LENGTH <= len(key) <= MAX_LENGTH and key not in _EMPTY_VALUES


def _origin(analyse_name: str | None, entity_name: str | None) -> str | None:
    parts = [f"Analyse {analyse_name}" if analyse_name else None, entity_name]
    return " · ".join(part for part in parts if part) or None


def _item_id(prefix: str, key: str) -> str:
    return f"{prefix}:{hashlib.sha256(key.encode()).hexdigest()[:16]}"


def _most_common(values: Sequence[str]) -> str:
    return Counter(values).most_common(1)[0][0]


class DossierLinkRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def between(
        self, user: RequestContext, ids: Collection[uuid.UUID], *, touching: Collection[uuid.UUID] = ()
    ) -> list[SharedItemOut]:
        """Les points communs à au moins deux des dossiers `ids`, les plus partagés d'abord. Avec `touching`, seulement
        ceux d'au moins un de ces dossiers."""
        if len(ids) < 2:
            return []
        items = [*await self._values(user, ids), *await self._documents(user, ids)]
        if touching:
            items = [item for item in items if set(item.dossier_ids) & set(touching)]
        items.sort(key=lambda item: (-len(item.dossier_ids), item.kind != "identifier", item.label.casefold(), item.id))
        return items[:MAX_ITEMS]

    async def holders(self, user: RequestContext, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
        """Les autres dossiers visibles qui partagent un point commun avec ceux de `ids` : pour chacun, lesquels."""
        found: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        value_keys = _linkable(Dossier.id.label("id"), normalized_value().label("key")).where(
            visible_clause(user), Dossier.id.in_(ids)
        )
        file_keys = (
            select(DossierDocument.dossier_id.label("id"), DossierDocument.file_hash.label("key"))
            .join(Dossier, Dossier.id == DossierDocument.dossier_id)
            .where(visible_clause(user), Dossier.id.in_(ids), DossierDocument.file_hash.is_not(None))
        )
        for mine_statement, others_of in (
            (value_keys, lambda keys: self._holders_of_values(user, keys)),
            (file_keys, lambda keys: self._holders_of_files(user, keys)),
        ):
            mine: dict[str, set[uuid.UUID]] = defaultdict(set)
            for row in await self.db.execute(mine_statement):
                if _is_meaningful(row.key):
                    mine[row.key].add(row.id)
            if not mine:
                continue
            others = await others_of(list(mine))
            limit = await self._common_limit(user)
            for key, holders in others.items():
                if len(holders) > limit:
                    continue
                for other in holders - set(ids):
                    found[other] |= mine[key]
        return found

    async def _common_limit(self, user: RequestContext) -> int:
        total = await self.db.scalar(select(func.count()).select_from(Dossier).where(visible_clause(user)))
        return max(COMMON_FLOOR, int((total or 0) * COMMON_SHARE))

    async def _holders_of_values(self, user: RequestContext, keys: list[str]) -> dict[str, set[uuid.UUID]]:
        key = normalized_value()
        matching = select(AnalysisElementVersion.id).where(key.in_(keys)).cte().prefix_with("MATERIALIZED")
        rows = await self.db.execute(
            _linkable(key.label("key"), Dossier.id.label("id"))
            # Les versions d'abord, par leur index : le planificateur parcourrait sinon toutes les valeurs.
            .where(visible_clause(user), AnalysisElementVersion.id.in_(select(matching.c.id)))
            .distinct()
        )
        found: dict[str, set[uuid.UUID]] = defaultdict(set)
        for row in rows:
            found[row.key].add(row.id)
        return found

    async def _holders_of_files(self, user: RequestContext, keys: list[str]) -> dict[str, set[uuid.UUID]]:
        rows = await self.db.execute(
            select(DossierDocument.file_hash.label("key"), Dossier.id.label("id"))
            .join(Dossier, Dossier.id == DossierDocument.dossier_id)
            .where(visible_clause(user), DossierDocument.file_hash.in_(keys))
            .distinct()
        )
        found: dict[str, set[uuid.UUID]] = defaultdict(set)
        for row in rows:
            found[row.key].add(row.id)
        return found

    async def _values(self, user: RequestContext, ids: Collection[uuid.UUID]) -> list[SharedItemOut]:
        key = normalized_value()
        found_rows = (
            await self.db.execute(
                _linkable(
                    key.label("key"),
                    value_text().label("value"),
                    Dossier.id.label("dossier_id"),
                    AnalysisElement.document_id,
                    AnalysisElement.first_page_number,
                    AnalysisElement.definition_name,
                    EntityDefinition.type,
                    Analyse.name.label("analyse_name"),
                    DossierDocument.name.label("document_name"),
                )
                .outerjoin(Analyse, Analyse.id == Dossier.analyse_id)
                .outerjoin(DossierDocument, DossierDocument.id == AnalysisElement.document_id)
                .where(visible_clause(user), Dossier.id.in_(ids))
                .order_by(Dossier.id, DossierDocument.name, AnalysisElement.first_page_number, AnalysisElement.id)
            )
        ).all()
        sharers: dict[str, set[uuid.UUID]] = defaultdict(set)
        for row in found_rows:
            if _is_meaningful(row.key):
                sharers[row.key].add(row.dossier_id)
        rows = [row for row in found_rows if len(sharers.get(row.key, ())) > 1]
        if not rows:
            return []

        everywhere = await self._holders_of_values(user, list({row.key for row in rows}))
        limit = await self._common_limit(user)
        grouped: dict[str, list] = defaultdict(list)
        for row in rows:
            if len(everywhere[row.key]) <= limit:
                grouped[row.key].append(row)

        items = []
        for value, found in grouped.items():
            origins = [_origin(row.analyse_name, row.definition_name) for row in found]
            occurrences = [
                LinkOccurrenceOut(
                    dossier_id=row.dossier_id,
                    document_id=row.document_id,
                    document_name=row.document_name,
                    page=row.first_page_number,
                    text=row.value,
                    origin=origin,
                )
                for row, origin in zip(found, origins, strict=True)
            ]
            identifier = any(row.type == EntityType.IDENTIFIANT for row in found)
            items.append(
                self._item(
                    "value",
                    value,
                    kind="identifier" if identifier else "value",
                    label=_most_common([row.value for row in found]),
                    occurrences=occurrences,
                )
            )
        return items

    async def _documents(self, user: RequestContext, ids: Collection[uuid.UUID]) -> list[SharedItemOut]:
        among = [visible_clause(user), Dossier.id.in_(ids), DossierDocument.file_hash.is_not(None)]

        def documents(*columns: Any) -> Select:
            return select(*columns).select_from(DossierDocument).join(Dossier, Dossier.id == DossierDocument.dossier_id)

        shared = (
            documents(DossierDocument.file_hash)
            .where(*among)
            .group_by(DossierDocument.file_hash)
            .having(func.count(distinct(Dossier.id)) > 1)
        )
        rows = (
            await self.db.execute(
                documents(
                    DossierDocument.file_hash,
                    DossierDocument.id,
                    DossierDocument.name,
                    DossierDocument.dossier_id,
                )
                .where(*among, DossierDocument.file_hash.in_(shared))
                .order_by(DossierDocument.file_hash, DossierDocument.dossier_id, DossierDocument.name)
            )
        ).all()
        if not rows:
            return []

        everywhere = await self._holders_of_files(user, list({row.file_hash for row in rows}))
        limit = await self._common_limit(user)
        grouped: dict[str, list] = defaultdict(list)
        for row in rows:
            if len(everywhere[row.file_hash]) <= limit:
                grouped[row.file_hash].append(row)
        return [
            self._item(
                "document",
                file_hash,
                kind="document",
                label=_most_common([row.name for row in found]),
                occurrences=[
                    LinkOccurrenceOut(dossier_id=row.dossier_id, document_id=row.id, document_name=row.name)
                    for row in found
                ],
            )
            for file_hash, found in grouped.items()
        ]

    @staticmethod
    def _item(prefix: str, key: str, *, kind: str, label: str, occurrences: list[LinkOccurrenceOut]) -> SharedItemOut:
        per_dossier: Counter[uuid.UUID] = Counter()
        kept = []
        for occurrence in occurrences:
            per_dossier[occurrence.dossier_id] += 1
            if per_dossier[occurrence.dossier_id] <= MAX_OCCURRENCES_PER_DOSSIER:
                kept.append(occurrence)
        return SharedItemOut(
            id=_item_id(prefix, key), kind=kind, label=label, dossier_ids=list(per_dossier), occurrences=kept
        )
