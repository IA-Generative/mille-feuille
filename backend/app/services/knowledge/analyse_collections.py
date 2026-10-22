"""Les collections de la base de connaissances que l'analyse autorise.

Comme les outils d'un agent, seules les collections **ajoutées** sont contrôlées : une collection déjà choisie reste
acceptée même si elle est devenue inaccessible (fournisseur, droit retiré, collection supprimée), pour qu'on puisse
modifier le reste de la liste. L'interface la signale « indisponible » et la personne la retire.

Les droits sont ceux de **la personne qui regarde ou qui ajoute** : un fournisseur répond selon son identité. Le nom
enregistré est celui que le fournisseur renvoie, jamais celui que le client prétend."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.knowledge_source import KnowledgeSource
from app.repositories.knowledge_source_repository import KnowledgeSourceRepository
from app.schemas.knowledge_collection import KnowledgeCollectionOut, KnowledgeCollectionRef
from app.services.knowledge.client import KnowledgeClient, KnowledgeError
from app.services.knowledge.connection import prepare_call
from app.services.knowledge.contract import Collection, LookupResult
from app.services.tools.credentials import CredentialsUnavailableError
from app.services.tools.identity_tokens import IdentityTokens
from app.services.tools.url_guard import UnsafeUrlError
from app.services.tools.visibility import can_view_server

LOOKUP_BATCH = 100  # le maximum du contrat pour une requête d'identifiants


@dataclass(frozen=True)
class RefusedCollection:
    source_id: uuid.UUID
    collection_id: str
    reason: str


class CollectionsRefusedError(ValueError):
    """Des collections ne peuvent pas être autorisées ; `refused` dit lesquelles et pourquoi."""

    def __init__(self, refused: Sequence[RefusedCollection]) -> None:
        super().__init__(f"{len(refused)} collection(s) refusée(s)")
        self.refused = list(refused)

    @property
    def message(self) -> str:
        return "Ces collections ne peuvent pas être utilisées : " + ", ".join(
            f"{r.collection_id} ({r.reason})" for r in self.refused
        )


REASONS = {
    "not_found": "introuvable chez le fournisseur",
    "forbidden": "accès refusé",
    "source_unavailable": "source inaccessible ou qui ne répond pas",
}


async def _lookup(
    source: KnowledgeSource,
    ids: list[str],
    user: RequestContext,
    client: KnowledgeClient,
    identity_tokens: IdentityTokens,
) -> LookupResult:
    """Retrouve ces collections chez le fournisseur, avec l'identité de la personne. Lève `KnowledgeError` si le
    fournisseur est injoignable ou refuse (`UnsafeUrlError` et `CredentialsUnavailableError` y sont ramenées)."""
    found: list[Collection] = []
    missing = []
    try:
        url, headers = await prepare_call(
            source.url,
            source.auth_mode,
            acting_user=user.user_id,
            audience=source.audience,
            identity_tokens=identity_tokens,
        )
        for start in range(0, len(ids), LOOKUP_BATCH):
            result = await client.lookup(url, headers, ids[start : start + LOOKUP_BATCH])
            found.extend(result.items)
            missing.extend(result.missing)
    except (UnsafeUrlError, CredentialsUnavailableError) as error:
        raise KnowledgeError("unavailable") from error
    return LookupResult(items=found, missing=missing)


def _by_source(refs: Sequence[KnowledgeCollectionRef | dict]) -> dict[uuid.UUID, list[str]]:
    grouped: dict[uuid.UUID, list[str]] = {}
    for ref in refs:
        source_id = ref.source_id if isinstance(ref, KnowledgeCollectionRef) else uuid.UUID(str(ref["source_id"]))
        collection_id = ref.collection_id if isinstance(ref, KnowledgeCollectionRef) else ref["collection_id"]
        grouped.setdefault(source_id, []).append(collection_id)
    return grouped


async def validate_collections(
    db: AsyncSession,
    user: RequestContext,
    client: KnowledgeClient,
    identity_tokens: IdentityTokens,
    refs: Sequence[KnowledgeCollectionRef],
    *,
    already: Sequence[dict] = (),
) -> list[dict]:
    """La liste à enregistrer (sans doublon, dans l'ordre demandé), ou lève `CollectionsRefusedError`. `already` : ce
    que l'analyse a déjà, repris tel quel (nom enregistré compris)."""
    stored = {(str(item["source_id"]), item["collection_id"]): item for item in already}
    unique: dict[tuple[str, str], KnowledgeCollectionRef] = {}
    for ref in refs:
        unique.setdefault((str(ref.source_id), ref.collection_id), ref)

    repository = KnowledgeSourceRepository(db)
    refused: list[RefusedCollection] = []
    names: dict[tuple[str, str], str] = {}
    for source_id, collection_ids in _by_source([r for key, r in unique.items() if key not in stored]).items():
        source = await repository.get(source_id)
        if source is None or not can_view_server(user, source):
            refused.extend(RefusedCollection(source_id, c, REASONS["source_unavailable"]) for c in collection_ids)
            continue
        try:
            result = await _lookup(source, collection_ids, user, client, identity_tokens)
        except KnowledgeError:
            refused.extend(RefusedCollection(source_id, c, REASONS["source_unavailable"]) for c in collection_ids)
            continue
        names.update({(str(source_id), c.id): c.name for c in result.items})
        refused.extend(RefusedCollection(source_id, m.id, REASONS[m.reason]) for m in result.missing)
        found_ids = {c.id for c in result.items} | {m.id for m in result.missing}
        # Le fournisseur n'a rien dit d'une collection demandée : on ne l'ajoute pas sur une supposition.
        refused.extend(
            RefusedCollection(source_id, c, REASONS["not_found"]) for c in collection_ids if c not in found_ids
        )
    if refused:
        raise CollectionsRefusedError(refused)
    return [
        stored[key] if key in stored else {"source_id": key[0], "collection_id": key[1], "name": names[key]}
        for key in unique
    ]


async def describe_collections(
    db: AsyncSession,
    user: RequestContext,
    client: KnowledgeClient,
    identity_tokens: IdentityTokens,
    stored: Sequence[dict],
) -> list[KnowledgeCollectionOut]:
    """L'état de chaque collection choisie **pour cette personne**, avec le nom à jour. Un fournisseur qui ne répond pas
    n'empêche pas d'afficher les autres."""
    repository = KnowledgeSourceRepository(db)
    state: dict[tuple[str, str], tuple[str, str]] = {}  # (source, collection) -> (nom à jour, statut)
    source_names: dict[str, str] = {}
    for source_id, collection_ids in _by_source(stored).items():
        source = await repository.get(source_id)
        visible = source is not None and can_view_server(user, source)
        source_names[str(source_id)] = source.name if visible else ""
        if not visible:
            continue
        try:
            result = await _lookup(source, collection_ids, user, client, identity_tokens)
        except KnowledgeError:
            continue
        for collection in result.items:
            state[(str(source_id), collection.id)] = (collection.name, "available")
        for missing in result.missing:
            state[(str(source_id), missing.id)] = ("", missing.reason)
    out = []
    for item in stored:
        key = (str(item["source_id"]), item["collection_id"])
        name, status = state.get(key, ("", "source_unavailable"))
        out.append(
            KnowledgeCollectionOut(
                source_id=uuid.UUID(key[0]),
                collection_id=key[1],
                name=name or item["name"],
                source_name=source_names.get(key[0], ""),
                status=status,
            )
        )
    return out
