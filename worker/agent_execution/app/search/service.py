"""Les opérations d'indexation d'un dossier, de bout en bout : lire les réglages au backend, écrire dans Qdrant, rendre
compte. Les tâches Celery (`app.tasks.search_index`) ne font qu'appeler ces fonctions.

Reconstruction blue/green : le nouvel index (`dossier_<id>_<empreinte>`) se construit à côté de l'actif, qui répond
encore à toutes les recherches. La construction est une **réconciliation** répétée jusqu'à ce qu'il n'y ait plus rien
à faire (les documents ajoutés ou retirés pendant la construction sont donc rattrapés), puis l'alias bascule en une
opération atomique, puis une dernière réconciliation rattrape ce qui a été écrit entre-temps. L'ancien index est gardé
jusqu'à la validation de la personne, ou le retour arrière."""

import logging

import httpx

from app import api_client
from app.search import indexer, store

logger = logging.getLogger(__name__)

# Passes de réconciliation avant la bascule : un dossier qui change plus vite que ça est basculé quand même, la
# réconciliation finale rattrape le reste.
MAX_PASSES = 5


def _fresh_dossier(client: httpx.Client, dossier_id: str) -> dict:
    return api_client.get_dossier(client, dossier_id)


def _only(dossier: dict, document_id: str) -> dict:
    return {**dossier, "documents": [d for d in dossier.get("documents", []) if d["id"] == document_id]}


def _swap_once_ready(qdrant, dossier_id: str, collection: str) -> None:
    """Donne un alias au dossier la première fois. Deux documents qui finissent en même temps tentent la même bascule :
    la perdante la refait, et le résultat est le même."""
    if store.active_collection(qdrant, dossier_id) is not None:
        return
    try:
        store.swap_alias(qdrant, dossier_id, collection)
    except Exception:
        if store.active_collection(qdrant, dossier_id) != collection:
            raise


def index_document(dossier_id: str, document_id: str) -> None:
    """Indexe les pages d'un document dans l'index actif du dossier, avec les réglages de cet index (ceux de l'analyse
    pour le tout premier document)."""
    with api_client.get_client() as client:
        config = api_client.get_search_config(client, dossier_id)
        settings, fingerprint = config.get("index_settings"), config.get("index_fingerprint")
        if settings is None:
            settings, fingerprint = config.get("effective"), config.get("fingerprint")
        if settings is None:
            logger.warning("Dossier %s non indexé : %s", dossier_id, config.get("problem"))
            return
        qdrant = store.get_client()
        collection = store.active_collection(qdrant, dossier_id) or store.collection_name(dossier_id, fingerprint)
        api_client.report_search_index(
            client, dossier_id, status="indexing", chunk_count=0, fingerprint=fingerprint, settings=settings
        )
        try:
            dossier = _only(_fresh_dossier(client, dossier_id), document_id)
            indexer.reconcile(qdrant, collection, dossier, settings=settings, fingerprint=fingerprint, prune=False)
            if qdrant.collection_exists(collection):
                _swap_once_ready(qdrant, dossier_id, collection)
        except Exception as error:
            logger.exception("Indexation du document %s impossible", document_id)
            api_client.report_search_index(client, dossier_id, status="error", error=str(error)[:500])
            raise
        total = store.count(qdrant, collection) if qdrant.collection_exists(collection) else 0
        api_client.report_search_index(client, dossier_id, status="ready", chunk_count=total)


def remove_document(dossier_id: str, document_id: str) -> None:
    """Retire les passages d'un document de l'index actif et de celui en construction."""
    qdrant = store.get_client()
    with api_client.get_client() as client:
        config = api_client.get_search_config(client, dossier_id)
    names = {store.active_collection(qdrant, dossier_id)}
    if config.get("rebuild"):
        names.add(store.collection_name(dossier_id, config["rebuild"]["target_fingerprint"]))
    for name in filter(None, names):
        if qdrant.collection_exists(name):
            store.delete_document(qdrant, name, document_id)


def rebuild_index(rebuild_id: str) -> None:
    with api_client.get_client() as client:
        rebuild = api_client.get_index_rebuild(client, rebuild_id)
        if rebuild["status"] != "building":
            return
        dossier_id = rebuild["dossier_id"]
        config = api_client.get_search_config(client, dossier_id)
        settings, target = config["rebuild_target_settings"], rebuild["target_fingerprint"]
        qdrant = store.get_client()
        next_collection = store.collection_name(dossier_id, target)
        try:
            _build_and_swap(client, qdrant, rebuild, dossier_id, settings, target, next_collection)
        except Exception as error:
            logger.exception("Reconstruction %s impossible", rebuild_id)
            if store.active_collection(qdrant, dossier_id) != next_collection:
                store.drop_collection(qdrant, next_collection)
            api_client.report_index_rebuild(client, rebuild_id, status="failed", error=str(error)[:500])


def _progress(client: httpx.Client, rebuild_id: str, total: int, done: int) -> None:
    api_client.report_index_rebuild(client, rebuild_id, total_pages=total, done_pages=min(done, total))


def _build_and_swap(
    client: httpx.Client, qdrant, rebuild: dict, dossier_id: str, settings: dict, target: str, next_collection: str
) -> None:
    rebuild_id = rebuild["id"]
    active = store.active_collection(qdrant, dossier_id)
    dossier = _fresh_dossier(client, dossier_id)
    pages = sum(1 for d in dossier.get("documents", []) for p in d.get("pages", []) if (p.get("content") or "").strip())
    done = 0
    _progress(client, rebuild_id, pages, done)

    def on_page(_chunks: int) -> None:
        nonlocal done
        done += 1
        _progress(client, rebuild_id, pages, done)

    for _ in range(MAX_PASSES):
        result = indexer.reconcile(
            qdrant,
            next_collection,
            _fresh_dossier(client, dossier_id),
            settings=settings,
            fingerprint=target,
            on_page=on_page,
        )
        if not result.changed:
            break
        if api_client.get_index_rebuild(client, rebuild_id)["status"] != "building":
            # Annulée pendant la construction : on laisse le retour arrière nettoyer.
            return

    if not qdrant.collection_exists(next_collection):
        # Dossier sans texte : une collection vide sert quand même d'index (la recherche répond « rien »).
        raise RuntimeError("Aucun texte à indexer dans ce dossier")

    previous = store.swap_alias(qdrant, dossier_id, next_collection) if active != next_collection else active
    api_client.report_search_index(
        client,
        dossier_id,
        status="ready",
        chunk_count=store.count(qdrant, next_collection),
        fingerprint=target,
        settings=settings,
        replace_settings=True,
    )
    # Sans ancien index, il n'y a rien à valider ni à rétablir : la reconstruction est terminée.
    had_previous = previous is not None and previous != next_collection
    api_client.report_index_rebuild(client, rebuild_id, status="swapped" if had_previous else "finalized")

    # Ce qui a été écrit pendant la bascule.
    indexer.reconcile(
        qdrant, next_collection, _fresh_dossier(client, dossier_id), settings=settings, fingerprint=target
    )
    api_client.report_search_index(client, dossier_id, status="ready", chunk_count=store.count(qdrant, next_collection))


def finalize_rebuild(rebuild_id: str) -> None:
    """La bascule est validée : l'ancien index n'a plus de raison d'être."""
    with api_client.get_client() as client:
        rebuild = api_client.get_index_rebuild(client, rebuild_id)
    previous = rebuild.get("previous_fingerprint")
    if not previous:
        return
    qdrant = store.get_client()
    old = store.collection_name(rebuild["dossier_id"], previous)
    if store.active_collection(qdrant, rebuild["dossier_id"]) != old:
        store.drop_collection(qdrant, old)


def rollback_rebuild(rebuild_id: str) -> None:
    """Abandonne la reconstruction : l'alias revient sur l'ancien index (si la bascule avait eu lieu) et le nouvel
    index est supprimé."""
    with api_client.get_client() as client:
        rebuild = api_client.get_index_rebuild(client, rebuild_id)
        dossier_id = rebuild["dossier_id"]
        qdrant = store.get_client()
        target = store.collection_name(dossier_id, rebuild["target_fingerprint"])
        previous = rebuild.get("previous_fingerprint")
        old = store.collection_name(dossier_id, previous) if previous else None
        if old and store.active_collection(qdrant, dossier_id) == target and qdrant.collection_exists(old):
            store.swap_alias(qdrant, dossier_id, old)
            api_client.report_search_index(client, dossier_id, status="ready", chunk_count=store.count(qdrant, old))
        if store.active_collection(qdrant, dossier_id) != target:
            store.drop_collection(qdrant, target)


def drop_dossier_index(dossier_id: str) -> None:
    store.drop_dossier(store.get_client(), dossier_id)
