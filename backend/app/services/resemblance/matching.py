"""Ce que des dossiers ont en commun au sens d'un thème (#649) : **tous** ses critères à la fois.

La même fonction sert au calcul (tous les dossiers) et à la lecture (les seuls dossiers visibles d'une page de
groupes), pour que les preuves affichées correspondent toujours aux valeurs actuelles. Aucune extraction : seules les
valeurs déjà extraites par les analyses et les empreintes de fichiers sont lues."""

import hashlib
import itertools
import json
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analyse import Analyse
from app.models.dossier import Dossier, DossierDocument
from app.models.dossier_analysis import AnalysisElement
from app.repositories.dossier_link_repository import (
    LINKED_KINDS,
    MAX_OCCURRENCES_PER_DOSSIER,
    is_meaningful,
    normalized_value,
)
from app.schemas.dossier_search import LinkOccurrenceOut
from app.services.retained_values import retained_values, value_text

# Un dossier aux très nombreuses valeurs (une liste de personnes) ne doit pas faire exploser les combinaisons.
MAX_VALUES_PER_CRITERION = 20
MAX_COMBINATIONS_PER_DOSSIER = 100


@dataclass
class Group:
    key: str
    # Ce qui est partagé, un libellé par critère.
    labels: list[str] = field(default_factory=list)
    dossiers: list[uuid.UUID] = field(default_factory=list)
    occurrences: list[LinkOccurrenceOut] = field(default_factory=list)


async def _values(
    db: AsyncSession, criterion: dict, where: list[ColumnElement[bool]]
) -> dict[uuid.UUID, dict[str, list[tuple[str, LinkOccurrenceOut]]]]:
    """Par dossier, par clé : (libellé, preuve) de ce que le critère y trouve."""
    found: dict = defaultdict(lambda: defaultdict(list))
    if criterion["origin"] == "file":
        rows = await db.execute(
            select(Dossier.id, DossierDocument.id, DossierDocument.name, DossierDocument.file_hash)
            .join(DossierDocument, DossierDocument.dossier_id == Dossier.id)
            .where(DossierDocument.file_hash.is_not(None), *where)
            .order_by(Dossier.id, DossierDocument.name)
        )
        for dossier_id, document_id, name, file_hash in rows:
            proof = LinkOccurrenceOut(dossier_id=dossier_id, document_id=document_id, document_name=name)
            found[dossier_id][file_hash].append((name, proof))
        return found

    rows = await db.execute(
        retained_values(
            LINKED_KINDS,
            normalized_value().label("key"),
            value_text().label("value"),
            Dossier.id.label("dossier_id"),
            AnalysisElement.document_id,
            AnalysisElement.first_page_number,
            AnalysisElement.definition_name,
            Analyse.name.label("analyse_name"),
            DossierDocument.name.label("document_name"),
        )
        .outerjoin(Analyse, Analyse.id == Dossier.analyse_id)
        .outerjoin(DossierDocument, DossierDocument.id == AnalysisElement.document_id)
        .where(AnalysisElement.definition_id.in_([uuid.UUID(i) for i in criterion["entity_ids"]]), *where)
        .order_by(Dossier.id, AnalysisElement.first_page_number, AnalysisElement.id)
    )
    for row in rows:
        if not is_meaningful(row.key):
            continue
        origin = " · ".join(p for p in (row.analyse_name and f"Analyse {row.analyse_name}", row.definition_name) if p)
        proof = LinkOccurrenceOut(
            dossier_id=row.dossier_id,
            document_id=row.document_id,
            document_name=row.document_name,
            page=row.first_page_number,
            text=row.value,
            origin=origin or None,
        )
        found[row.dossier_id][row.key].append((row.value, proof))
    return found


async def find_groups(
    db: AsyncSession, criteria: list[dict], scope: str, *, where: list[ColumnElement[bool]] | None = None
) -> dict[str, Group]:
    """Les groupes d'au moins deux dossiers, parmi ceux que `where` retient."""
    where = where or []
    per_criterion = [await _values(db, criterion, where) for criterion in criteria]
    if not per_criterion:
        return {}
    candidates = set.intersection(*[set(values) for values in per_criterion])
    if len(candidates) < 2:
        return {}

    themes = dict(
        (
            await db.execute(
                select(Dossier.id, Analyse.theme_id)
                .outerjoin(Analyse, Analyse.id == Dossier.analyse_id)
                .where(Dossier.id.in_(list(candidates)))
            )
        ).all()
    )
    members: dict[tuple, list[uuid.UUID]] = defaultdict(list)
    for dossier_id in sorted(candidates, key=str):
        keys = [sorted(values[dossier_id])[:MAX_VALUES_PER_CRITERION] for values in per_criterion]
        # Au sein d'un même thème d'analyse : un groupe par thème.
        part = str(themes.get(dossier_id) or "") if scope == "within" else ""
        for combination in itertools.islice(itertools.product(*keys), MAX_COMBINATIONS_PER_DOSSIER):
            members[(combination, part)].append(dossier_id)

    groups = {}
    for (combination, part), dossiers in members.items():
        if len(dossiers) < 2 or (scope == "across" and len({themes.get(d) for d in dossiers}) < 2):
            continue
        signature = json.dumps([[c["id"] for c in criteria], combination, part], ensure_ascii=False)
        group = Group(key=hashlib.sha256(signature.encode()).hexdigest(), dossiers=dossiers)
        for values, key in zip(per_criterion, combination, strict=True):
            found = [pair for d in dossiers for pair in values[d][key]]
            group.labels.append(Counter(label for label, _ in found).most_common(1)[0][0])
            for d in dossiers:
                group.occurrences += [proof for _, proof in values[d][key][:MAX_OCCURRENCES_PER_DOSSIER]]
        groups[group.key] = group
    return groups
