"""Les opérations d'indexation d'un dossier, de bout en bout : lire les réglages, écrire dans Qdrant, rendre compte
à `SearchIndexService`. Le découpage et les embeddings sont bloquants : ils tournent dans des threads, la boucle
du backend reste libre.

Reconstruction blue/green : le nouvel index (`dossier_<id>_<empreinte>`) se construit à côté de l'actif, qui répond
encore à toutes les recherches. La construction est une **réconciliation** répétée jusqu'à ce qu'il n'y ait plus rien
à faire (les documents ajoutés ou retirés pendant la construction sont donc rattrapés), puis l'alias bascule en une
opération atomique, puis une dernière réconciliation rattrape ce qui a été écrit entre-temps. L'ancien index est gardé
jusqu'à la validation de la personne, ou le retour arrière. Une réconciliation ne refait que la différence : un travail
interrompu se reprend simplement en le relançant."""

import asyncio
import logging
import uuid

from app.agent.documents import load_dossier
from app.db import async_session_factory
from app.models.search_index import IndexRebuild, IndexRebuildStatus, SearchIndexStatus
from app.schemas.search_index import RebuildReport, SearchIndexReport
from app.services.search import indexer
from app.services.search import qdrant_store as store

logger = logging.getLogger(__name__)

# Passes de réconciliation avant la bascule : un dossier qui change plus vite que ça est basculé quand même, la
# réconciliation finale rattrape le reste.
MAX_PASSES = 5


def _service(db):  # noqa: ANN001, ANN202
    # Importé ici : `SearchIndexService` lance ces travaux (import circulaire sinon).
    from app.services.search.index_service import SearchIndexService

    return SearchIndexService(db)


async def _config(dossier_id: str):  # noqa: ANN202
    async with async_session_factory() as db:
        return await _service(db).config(uuid.UUID(dossier_id))


async def _report_index(dossier_id: str, report: SearchIndexReport) -> None:
    async with async_session_factory() as db:
        await _service(db).report_index(uuid.UUID(dossier_id), report)


async def _report_rebuild(rebuild_id: str, report: RebuildReport) -> None:
    async with async_session_factory() as db:
        await _service(db).report_rebuild(uuid.UUID(rebuild_id), report)


async def _rebuild(rebuild_id: str) -> IndexRebuild | None:
    async with async_session_factory() as db:
        return await db.get(IndexRebuild, uuid.UUID(rebuild_id))


async def _fresh_dossier(dossier_id: str) -> dict:
    async with async_session_factory() as db:
        return await load_dossier(db, dossier_id)


def _only(dossier: dict, document_id: str) -> dict:
    return {**dossier, "documents": [d for d in dossier.get("documents", []) if d["id"] == document_id]}


def _swap_once_ready(qdrant, dossier_id: str, collection: str) -> None:  # noqa: ANN001
    """Donne un alias au dossier la première fois. Deux documents qui finissent en même temps tentent la même bascule :
    la perdante la refait, et le résultat est le même."""
    if store.active_collection(qdrant, dossier_id) is not None:
        return
    try:
        store.swap_alias(qdrant, dossier_id, collection)
    except Exception:
        if store.active_collection(qdrant, dossier_id) != collection:
            raise


def _count(qdrant, collection: str) -> int:  # noqa: ANN001
    return store.count(qdrant, collection) if qdrant.collection_exists(collection) else 0


async def index_document(dossier_id: str, document_id: str) -> None:
    """Indexe les pages d'un document dans l'index actif du dossier, avec les réglages de cet index (ceux de l'analyse
    pour le tout premier document)."""
    config = await _config(dossier_id)
    settings, fingerprint = config.index_settings, config.index_fingerprint
    if settings is None:
        settings, fingerprint = config.effective, config.fingerprint
    if settings is None:
        logger.warning("Dossier %s non indexé : %s", dossier_id, config.problem)
        return
    qdrant = store.get_client()
    collection = await asyncio.to_thread(store.active_collection, qdrant, dossier_id) or store.collection_name(
        dossier_id, fingerprint
    )
    await _report_index(
        dossier_id,
        SearchIndexReport(status=SearchIndexStatus.INDEXING, chunk_count=0, fingerprint=fingerprint, settings=settings),
    )
    try:
        dossier = _only(await _fresh_dossier(dossier_id), document_id)
        await asyncio.to_thread(
            indexer.reconcile, qdrant, collection, dossier, settings=settings, fingerprint=fingerprint, prune=False
        )
        if await asyncio.to_thread(qdrant.collection_exists, collection):
            await asyncio.to_thread(_swap_once_ready, qdrant, dossier_id, collection)
    except Exception as error:
        logger.exception("Indexation du document %s impossible", document_id)
        await _report_index(dossier_id, SearchIndexReport(status=SearchIndexStatus.ERROR, error=str(error)[:500]))
        return
    total = await asyncio.to_thread(_count, qdrant, collection)
    await _report_index(dossier_id, SearchIndexReport(status=SearchIndexStatus.READY, chunk_count=total))


async def rebuild_index(rebuild_id: str) -> None:
    rebuild = await _rebuild(rebuild_id)
    if rebuild is None or rebuild.status != IndexRebuildStatus.BUILDING:
        return
    dossier_id = str(rebuild.dossier_id)
    settings, target = rebuild.target_settings, rebuild.target_fingerprint
    qdrant = store.get_client()
    next_collection = store.collection_name(dossier_id, target)
    try:
        await _build_and_swap(qdrant, rebuild_id, dossier_id, settings, target, next_collection)
    except Exception as error:
        logger.exception("Reconstruction %s impossible", rebuild_id)
        if await asyncio.to_thread(store.active_collection, qdrant, dossier_id) != next_collection:
            await asyncio.to_thread(store.drop_collection, qdrant, next_collection)
        await _report_rebuild(rebuild_id, RebuildReport(status=IndexRebuildStatus.FAILED, error=str(error)[:500]))


async def _build_and_swap(
    qdrant,  # noqa: ANN001
    rebuild_id: str,
    dossier_id: str,
    settings: dict,
    target: str,
    next_collection: str,
) -> None:
    loop = asyncio.get_running_loop()
    active = await asyncio.to_thread(store.active_collection, qdrant, dossier_id)
    dossier = await _fresh_dossier(dossier_id)
    pages = sum(1 for d in dossier.get("documents", []) for p in d.get("pages", []) if (p.get("content") or "").strip())
    done = 0
    await _report_rebuild(rebuild_id, RebuildReport(total_pages=pages, done_pages=0))

    def on_page(_chunks: int) -> None:
        # Appelé depuis le thread de la réconciliation : le compte rendu se fait sur la boucle du backend.
        nonlocal done
        done += 1
        report = RebuildReport(total_pages=pages, done_pages=min(done, pages))
        asyncio.run_coroutine_threadsafe(_report_rebuild(rebuild_id, report), loop).result(timeout=60)

    for _ in range(MAX_PASSES):
        result = await asyncio.to_thread(
            indexer.reconcile,
            qdrant,
            next_collection,
            await _fresh_dossier(dossier_id),
            settings=settings,
            fingerprint=target,
            on_page=on_page,
        )
        if not result.changed:
            break
        current = await _rebuild(rebuild_id)
        if current is None or current.status != IndexRebuildStatus.BUILDING:
            # Annulée pendant la construction : on laisse le retour arrière nettoyer.
            return

    if not await asyncio.to_thread(qdrant.collection_exists, next_collection):
        # Dossier sans texte : une collection vide sert quand même d'index (la recherche répond « rien »).
        raise RuntimeError("Aucun texte à indexer dans ce dossier")

    previous = (
        await asyncio.to_thread(store.swap_alias, qdrant, dossier_id, next_collection)
        if active != next_collection
        else active
    )
    await _report_index(
        dossier_id,
        SearchIndexReport(
            status=SearchIndexStatus.READY,
            chunk_count=await asyncio.to_thread(store.count, qdrant, next_collection),
            fingerprint=target,
            settings=settings,
            replace_settings=True,
        ),
    )
    # Sans ancien index, il n'y a rien à valider ni à rétablir : la reconstruction est terminée.
    had_previous = previous is not None and previous != next_collection
    await _report_rebuild(
        rebuild_id,
        RebuildReport(status=IndexRebuildStatus.SWAPPED if had_previous else IndexRebuildStatus.FINALIZED),
    )

    # Ce qui a été écrit pendant la bascule.
    await asyncio.to_thread(
        indexer.reconcile,
        qdrant,
        next_collection,
        await _fresh_dossier(dossier_id),
        settings=settings,
        fingerprint=target,
    )
    total = await asyncio.to_thread(store.count, qdrant, next_collection)
    await _report_index(dossier_id, SearchIndexReport(status=SearchIndexStatus.READY, chunk_count=total))


async def finalize_rebuild(rebuild_id: str) -> None:
    """La bascule est validée : l'ancien index n'a plus de raison d'être."""
    rebuild = await _rebuild(rebuild_id)
    if rebuild is None or not rebuild.previous_fingerprint:
        return
    dossier_id = str(rebuild.dossier_id)
    qdrant = store.get_client()
    old = store.collection_name(dossier_id, rebuild.previous_fingerprint)
    if await asyncio.to_thread(store.active_collection, qdrant, dossier_id) != old:
        await asyncio.to_thread(store.drop_collection, qdrant, old)


async def rollback_rebuild(rebuild_id: str) -> None:
    """Abandonne la reconstruction : l'alias revient sur l'ancien index (si la bascule avait eu lieu) et le nouvel
    index est supprimé."""
    rebuild = await _rebuild(rebuild_id)
    if rebuild is None:
        return
    dossier_id = str(rebuild.dossier_id)
    qdrant = store.get_client()
    target = store.collection_name(dossier_id, rebuild.target_fingerprint)
    old = store.collection_name(dossier_id, rebuild.previous_fingerprint) if rebuild.previous_fingerprint else None
    if (
        old
        and await asyncio.to_thread(store.active_collection, qdrant, dossier_id) == target
        and await asyncio.to_thread(qdrant.collection_exists, old)
    ):
        await asyncio.to_thread(store.swap_alias, qdrant, dossier_id, old)
        total = await asyncio.to_thread(store.count, qdrant, old)
        await _report_index(dossier_id, SearchIndexReport(status=SearchIndexStatus.READY, chunk_count=total))
    if await asyncio.to_thread(store.active_collection, qdrant, dossier_id) != target:
        await asyncio.to_thread(store.drop_collection, qdrant, target)


async def drop_dossier_index(dossier_id: str) -> None:
    await asyncio.to_thread(store.drop_dossier, store.get_client(), dossier_id)
