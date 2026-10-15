import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_client import (
    dispatch_dossier_pipeline,
)
from app.connectors import s3_connector
from app.core.security.ephemeral import EphemeralIdentity, get_ephemeral_identity
from app.db import get_db
from app.models.analyse import AgentTool, Analyse, EntityDefinition, LabelDefinition
from app.models.analyse_ephemere import AnalyseEphemere
from app.models.document_page import PredictionKind, PredictionSource
from app.models.dossier import Dossier, DossierStatus
from app.models.dossier_ephemere import DossierEphemere
from app.models.ephemeral_run_metrics import EphemeralRunMetrics
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_repository import DossierRepository
from app.repositories.ephemeral_repository import EphemeralRepository
from app.schemas.analyse import EntityDefinitionIn, LabelDefinitionIn
from app.schemas.ephemeral import (
    EphemeralAnalyseCreate,
    EphemeralAnalyseCreated,
    EphemeralAnalyseOut,
    EphemeralClassificationOut,
    EphemeralExtractionOut,
    EphemeralRunCreated,
    EphemeralRunOut,
    EphemeralRunSummary,
)
from app.schemas.ephemeral_metrics import FeedbackIn, FeedbackOut, GlobalMetricsOut, RunMetricsOut
from app.services import ephemeral_metrics
from app.services.ephemeral_results import COMBINED_RUN_PREFIX, to_classification_out, to_extraction_out, to_run_summary
from app.services.ephemeral_run_service import finalize_run, to_run_schema

router = APIRouter(prefix="/ephemeral", tags=["Ephemeral"], dependencies=[Depends(get_ephemeral_identity)])

# Cf. docs/ephemeral-api.md, section "Principe du TTL".
TTL_DEFAULT_HOURS = 24
TTL_MAX_HOURS = 17520  # 2 ans


def _reject_persist_for_env_key(identity: EphemeralIdentity, persist: bool) -> None:
    """Une requête authentifiée par la clé d'API de l'environnement ne peut rien conserver : 403 si `persist=true`."""
    if persist and identity.is_env_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cette clé d'API ne permet pas persist=true (non persistant)"
        )


async def _get_runnable_analyse_or_404(db: AsyncSession, analyse_id: uuid.UUID, identity: EphemeralIdentity) -> Analyse:
    """L'analyse sur laquelle lancer un run. Un jeton ou un compte peut aussi viser une analyse classique de la
    plateforme ; la clé d'API de l'environnement, non : elle n'atteint que les analyses éphémères qu'elle a créées
    (404 sinon, comme partout dans ce routeur)."""
    analyse = await AnalyseRepository(db).get(analyse_id)
    if analyse is not None and identity.is_env_key:
        record = await EphemeralRepository(db).get_analyse_ephemere(analyse_id)
        if record is None or record.created_by != identity.id:
            analyse = None
    if analyse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analyse introuvable")
    return analyse


async def _get_analyse_ephemere_or_404(
    repository: EphemeralRepository, analyse_id: uuid.UUID, identity: EphemeralIdentity
) -> AnalyseEphemere:
    """404, pas 403 : ne pas laisser deviner qu'un id existe mais appartient
    à quelqu'un d'autre. Scope strict aux analyses créées via ce routeur
    (cf. docs/ephemeral-api.md) - une Analyse classique de la plateforme n'a
    pas de ligne AnalyseEphemere et tombe dans le même 404."""
    record = await repository.get_analyse_ephemere(analyse_id)
    if record is None or record.created_by != identity.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analyse éphémère introuvable")
    return record


@router.post(
    "/analyses",
    response_model=EphemeralAnalyseCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Crée une analyse éphémère complète en un seul appel",
    description="Crée une analyse (classification, extraction, agents) en une seule requête, contrairement au "
    "flux standard de la plateforme (POST /api/analyses puis un appel par champ à configurer). "
    "`persist=false` (défaut) : purgée automatiquement une fois son TTL écoulé, calculé à la fin du "
    "dernier run l'ayant utilisée (jamais à la création) - voir docs/ephemeral-api.md. `persist=true` : "
    "conservée indéfiniment, comme une Analyse classique. L'id renvoyé est toujours celui d'une "
    "`Analyse` normale de la plateforme (une ligne `analyse_ephemere` y est simplement associée).",
)
async def create_ephemeral_analyse(
    body: EphemeralAnalyseCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> EphemeralAnalyseCreated:
    _reject_persist_for_env_key(identity, body.persist)
    analyse_repository = AnalyseRepository(db)
    analyse = await analyse_repository.create(
        name=body.name, description=body.description, multi_label=body.multi_label
    )
    # create() ne recharge pas les relations (labels/entities/agents) après
    # commit : sans ce re-fetch (via _base_query, eager load), les accéder
    # dans les update_* ci-dessous ferait un lazy-load hors contexte async.
    analyse = await analyse_repository.get(analyse.id)

    if body.classification_prompt:
        await analyse_repository.update_classification_prompt(analyse, body.classification_prompt)
    if body.labels:
        await analyse_repository.update_classification_labels(
            analyse, [LabelDefinition(name=lbl.name, definition=lbl.definition) for lbl in body.labels]
        )
    if body.extraction_prompt:
        await analyse_repository.update_extraction_prompt(analyse, body.extraction_prompt)
    if body.entities:
        await analyse_repository.update_extraction_entities(
            analyse,
            [EntityDefinition(name=ent.name, definition=ent.definition, type=ent.type) for ent in body.entities],
        )
    for agent in body.agents:
        await analyse_repository.add_agent(
            analyse,
            name=agent.name,
            prompt=agent.prompt,
            tools=[AgentTool(t) for t in agent.tools],
            output=agent.output,
            model=agent.model,
        )

    await EphemeralRepository(db).create_analyse_ephemere(
        analyse_id=analyse.id, persist=body.persist, created_by=identity.id
    )
    return EphemeralAnalyseCreated(analyse_id=analyse.id)


@router.get(
    "/analyses/{analyse_id}",
    response_model=EphemeralAnalyseOut,
    summary="Consulte une analyse éphémère",
    description="Scope strict : ne renvoie que les analyses créées via POST /api/ephemeral/analyses, et "
    "seulement à leur créateur (404 dans les deux autres cas - jamais 403, pour ne pas laisser deviner "
    "qu'un id existe mais appartient à quelqu'un d'autre). Une Analyse classique de la plateforme, même "
    "avec un id valide, tombe dans le même 404.",
    responses={404: {"description": "Analyse introuvable, pas éphémère, ou appartenant à un autre créateur."}},
)
async def get_ephemeral_analyse(
    analyse_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> EphemeralAnalyseOut:
    ephemeral_repository = EphemeralRepository(db)
    record = await _get_analyse_ephemere_or_404(ephemeral_repository, analyse_id, identity)

    analyse_repository = AnalyseRepository(db)
    analyse = await analyse_repository.get(analyse_id)
    if analyse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analyse éphémère introuvable")
    return EphemeralAnalyseOut(
        **analyse_repository.to_schema(analyse).model_dump(),
        persist=record.persist,
        expires_at=record.expires_at,
    )


@router.delete(
    "/analyses/{analyse_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprime une analyse éphémère immédiatement",
    description="Suppression immédiate, sans attendre le TTL. Même scope strict que le GET (404 si pas "
    "éphémère ou pas créée par l'appelant). 409 si des runs (dossier_ephemere) référencent encore cette "
    "analyse - supprimez-les d'abord (DELETE /api/ephemeral/runs/{id}) : la contrainte est portée par la "
    "base (FK Dossier.analyse_id, ondelete=RESTRICT), pas une vérification applicative séparée.",
    responses={
        404: {"description": "Analyse introuvable, pas éphémère, ou appartenant à un autre créateur."},
        409: {"description": "Des dossiers référencent encore cette analyse."},
    },
)
async def delete_ephemeral_analyse(
    analyse_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> None:
    ephemeral_repository = EphemeralRepository(db)
    await _get_analyse_ephemere_or_404(ephemeral_repository, analyse_id, identity)

    analyse_repository = AnalyseRepository(db)
    analyse = await analyse_repository.get(analyse_id)
    if analyse is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analyse éphémère introuvable")
    try:
        # La ligne AnalyseEphemere cascade avec l'Analyse (ondelete="CASCADE"),
        # pas besoin de la supprimer séparément.
        await analyse_repository.delete(analyse)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Des dossiers référencent encore cette analyse - supprimez-les d'abord",
        ) from error


def _validate_ttl_hours(ttl_hours: int | None) -> int:
    value = TTL_DEFAULT_HOURS if ttl_hours is None else ttl_hours
    if value <= 0 or value > TTL_MAX_HOURS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ttl_hours doit être compris entre 1 et {TTL_MAX_HOURS} (2 ans)",
        )
    return value


async def _read_upload_files(files: list[UploadFile]) -> list[tuple[str, bytes, str]]:
    return [(f.filename or "document", await f.read(), f.content_type or "application/octet-stream") for f in files]


async def _create_run(
    *,
    db: AsyncSession,
    identity: EphemeralIdentity,
    analyse: Analyse,
    files: list[tuple[str, bytes, str]],
    persist: bool,
    ttl_hours: int,
    name: str | None = None,
) -> Dossier:
    """Cœur commun aux flux A et B (et au serveur MCP, cf. app/mcp/server.py) :
    upload + lancement immédiat du pipeline complet (pas d'étape `launch`
    séparée, contrairement à /api/dossiers), puis pose de la ligne
    dossier_ephemere. Réutilise telle quelle la logique d'upload/lancement
    de dossiers.py.

    `files` : (nom, contenu, type MIME) déjà lus en mémoire - pas de
    `UploadFile` FastAPI ici, pour rester appelable depuis un contexte qui
    n'en a pas (le serveur MCP décode du base64, pas un multipart HTTP)."""
    dossier_repository = DossierRepository(db)
    dossier = await dossier_repository.create(name=name or f"Run éphémère {uuid.uuid4()}", analyse=analyse)

    documents = []
    for name, data, mimetype in files:
        s3_key = f"dossiers/{dossier.id}/{uuid.uuid4()}-{name or 'document'}"
        await run_in_threadpool(s3_connector.upload, s3_key, data, mimetype)
        documents.append({"name": name or "document", "size": len(data), "s3_key": s3_key, "mimetype": mimetype})
    created = await dossier_repository.add_documents(dossier, documents)
    document_ids = [str(document.id) for document in created]
    # add_documents() finit par un refresh(dossier) qui périme execution_steps
    # (accédée par launch() juste après) - même raison que le commentaire
    # équivalent dans dossiers.py:add_documents, un re-fetch recharge tout
    # via _base_query (populate_existing=True).
    dossier = await dossier_repository.get(dossier.id)

    await dossier_repository.launch(dossier, analyse)
    dispatch_dossier_pipeline(document_ids, str(dossier.id))

    ephemeral_repository = EphemeralRepository(db)
    analyse_ephemere = await ephemeral_repository.get_analyse_ephemere(analyse.id)
    await ephemeral_repository.create_dossier_ephemere(
        dossier_id=dossier.id,
        analyse_ephemere_id=analyse_ephemere.analyse_id if analyse_ephemere else None,
        persist=persist,
        ttl_hours=ttl_hours,
        created_by=identity.id,
    )
    # Pas `return dossier` : add_documents()/launch() réexpirent les
    # relations déjà chargées (même raison que le commentaire équivalent
    # dans dossiers.py:add_documents) - un re-fetch a le eager loading
    # complet de DossierRepository._base_query.
    return await dossier_repository.get(dossier.id)


@router.post(
    "/analyses/{analyse_id}/runs",
    response_model=EphemeralRunCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Lance un run sur une analyse déjà créée (flux A)",
    description="Multipart : fichiers + persist (form, défaut false) + ttl_hours (query, défaut 24h, max "
    "17520h/2 ans, 400 si hors bornes). `analyse_id` peut être une analyse éphémère ou une `Analyse` "
    "classique de la plateforme (dans ce dernier cas, l'analyse n'est jamais modifiée). Le pipeline "
    "complet (classification, extraction, agents) démarre immédiatement, sans appel `launch` séparé.",
    responses={
        400: {"description": "ttl_hours hors bornes (doit être entre 1 et 17520)."},
        404: {"description": "analyse_id introuvable (ni éphémère, ni classique)."},
    },
)
async def create_ephemeral_run_for_analyse(
    analyse_id: uuid.UUID,
    files: list[UploadFile],
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
    persist: Annotated[bool, Form()] = False,
    ttl_hours: Annotated[int | None, Query()] = None,
) -> EphemeralRunCreated:
    _reject_persist_for_env_key(identity, persist)
    analyse = await _get_runnable_analyse_or_404(db, analyse_id, identity)
    dossier = await _create_run(
        db=db,
        identity=identity,
        analyse=analyse,
        files=await _read_upload_files(files),
        persist=persist,
        ttl_hours=_validate_ttl_hours(ttl_hours),
    )
    return EphemeralRunCreated(run_id=dossier.id)


@router.post(
    "/runs",
    response_model=EphemeralRunCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Crée l'analyse et lance le run en un seul appel (flux B)",
    description="Équivalent du flux A (POST .../analyses/{id}/runs) sans passer par la création préalable "
    "de l'analyse : `analyse_id` (form) référence une analyse déjà existante, éphémère ou classique. Mêmes "
    "règles de TTL/persist et même déclenchement immédiat du pipeline complet que le flux A.",
    responses={
        400: {"description": "ttl_hours hors bornes (doit être entre 1 et 17520)."},
        404: {"description": "analyse_id introuvable (ni éphémère, ni classique)."},
    },
)
async def create_ephemeral_run(
    files: list[UploadFile],
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
    analyse_id: Annotated[uuid.UUID, Form()],
    persist: Annotated[bool, Form()] = False,
    ttl_hours: Annotated[int | None, Query()] = None,
) -> EphemeralRunCreated:
    _reject_persist_for_env_key(identity, persist)
    analyse = await _get_runnable_analyse_or_404(db, analyse_id, identity)
    dossier = await _create_run(
        db=db,
        identity=identity,
        analyse=analyse,
        files=await _read_upload_files(files),
        persist=persist,
        ttl_hours=_validate_ttl_hours(ttl_hours),
    )
    return EphemeralRunCreated(run_id=dossier.id)


async def _get_owned_run_or_404(
    db: AsyncSession, run_id: uuid.UUID, identity: EphemeralIdentity
) -> tuple[Dossier, DossierEphemere]:
    """404, pas 403 (même rationale que _get_analyse_ephemere_or_404) : scope
    strict aux dossiers créés via ce routeur et à leur créateur. Ne couvre que
    les runs encore actifs ou persist=True : un run terminé persist=false n'a
    plus de dossier, son résultat se lit via _get_run_out_or_404."""
    record = await EphemeralRepository(db).get_dossier_ephemere(run_id)
    if record is None or record.created_by != identity.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run éphémère introuvable")
    dossier = await DossierRepository(db).get(run_id)
    if dossier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run éphémère introuvable")
    return dossier, record


async def _get_run_out_or_404(db: AsyncSession, run_id: uuid.UUID, identity: EphemeralIdentity) -> EphemeralRunOut:
    """Le run vu par le client : dossier vivant s'il existe, sinon le résultat
    conservé après sa fin (ephemeral_results, cf. ephemeral_run_service)."""
    ephemeral_repository = EphemeralRepository(db)
    if await ephemeral_repository.get_dossier_ephemere(run_id) is not None:
        dossier, record = await _get_owned_run_or_404(db, run_id, identity)
        return to_run_schema(dossier, record)
    result = await ephemeral_repository.get_result(run_id)
    if result is None or result.created_by != identity.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run éphémère introuvable")
    return EphemeralRunOut.model_validate(result.payload)


@router.get(
    "/runs",
    response_model=list[EphemeralRunSummary],
    summary="Liste les runs de l'appelant",
    description="Runs en cours ou conservés (`persist=true`), puis résultats conservés des runs `persist=false` "
    "terminés, du plus récent au plus ancien (100 au plus). Même scope strict que GET /runs/{id} : uniquement "
    "ce que l'appelant a créé. Le détail d'un run se lit avec GET /runs/{id}.",
)
async def list_ephemeral_runs(
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> list[EphemeralRunSummary]:
    repository = EphemeralRepository(db)
    dossier_repository = DossierRepository(db)
    runs: list[EphemeralRunOut] = []
    for record in await repository.list_dossier_ephemeres(identity.id):
        dossier = await dossier_repository.get(record.dossier_id)
        if dossier is not None:
            runs.append(to_run_schema(dossier, record))
    runs.extend(EphemeralRunOut.model_validate(result.payload) for result in await repository.list_results(identity.id))
    runs.sort(key=lambda run: run.created_at, reverse=True)
    return [to_run_summary(run) for run in runs[:100]]


@router.get(
    "/runs/{run_id}",
    response_model=EphemeralRunOut,
    summary="Consulte un run éphémère (statut + résultats)",
    description="Statut en cours, puis résultats complets (classification, entités, sorties des agents) une "
    "fois terminé. Scope strict : ne renvoie que les runs créés via ce routeur, et seulement à leur "
    "créateur (404 dans les deux autres cas).",
    responses={404: {"description": "Run introuvable, pas éphémère, ou appartenant à un autre créateur."}},
)
async def get_ephemeral_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> EphemeralRunOut:
    return await _get_run_out_or_404(db, run_id, identity)


@router.post(
    "/runs/{run_id}/stop",
    response_model=EphemeralRunOut,
    summary="Arrête un run en cours",
    description="No-op si le run est déjà dans un état terminal (terminé/arrêté/échec) - même comportement "
    "que POST /api/dossiers/{id}/stop. Un run persist=false arrêté est finalisé comme un run terminé : "
    "son résultat reste consultable via GET jusqu'à expires_at, mais son dossier, ses fichiers et son analyse "
    "éphémère sont supprimés (voir docs/ephemeral-api.md). Un run persist=true reste intact.",
    responses={404: {"description": "Run introuvable, pas éphémère, ou appartenant à un autre créateur."}},
)
async def stop_ephemeral_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> EphemeralRunOut:
    ephemeral_repository = EphemeralRepository(db)
    if await ephemeral_repository.get_dossier_ephemere(run_id) is None:
        # Run déjà finalisé (résultat seul conservé) : rien à arrêter.
        return await _get_run_out_or_404(db, run_id, identity)
    dossier, _ = await _get_owned_run_or_404(db, run_id, identity)
    dossier_repository = DossierRepository(db)
    # No-op si déjà dans un état terminal (terminé/arrêté/échec) - même
    # comportement que POST /api/dossiers/{id}/stop.
    await dossier_repository.stop(dossier)
    dossier = await dossier_repository.get(run_id)
    # mark_dossier_terminal est idempotent (no-op si déjà posé) : appelé
    # systématiquement plutôt que seulement quand stop() vient d'agir, pour
    # rattraper un éventuel dossier déjà arrêté/terminé sans expires_at.
    await ephemeral_repository.mark_dossier_terminal(dossier)
    await finalize_run(db, run_id)
    return await _get_run_out_or_404(db, run_id, identity)


@router.delete(
    "/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Arrête (si besoin) et supprime un run immédiatement",
    description="Si le run est encore en_cours, l'arrête d'abord (même effet que POST .../stop), puis "
    "supprime immédiatement le dossier (documents, étapes d'exécution, résultats, fichiers S3) et le "
    "résultat conservé, sans attendre expires_at. Ne touche pas à l'analyse liée. Même scope strict que "
    "le GET.",
    responses={404: {"description": "Run introuvable, pas éphémère, ou appartenant à un autre créateur."}},
)
async def delete_ephemeral_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> None:
    ephemeral_repository = EphemeralRepository(db)
    if await ephemeral_repository.get_dossier_ephemere(run_id) is None:
        # Run finalisé : il ne reste que le résultat conservé.
        await _get_run_out_or_404(db, run_id, identity)  # 404 si absent ou pas à l'appelant
        await ephemeral_repository.delete_result(run_id)
        return
    dossier, _ = await _get_owned_run_or_404(db, run_id, identity)
    dossier_repository = DossierRepository(db)
    if dossier.status == DossierStatus.EN_COURS:
        await dossier_repository.stop(dossier)
        dossier = await dossier_repository.get(run_id)
    # delete_dossier refuse encore en_attente/en_cours : un run éphémère est
    # toujours lancé immédiatement à la création (_create_run), en_attente
    # ne devrait jamais se produire en pratique - pas de branche dédiée.
    await dossier_repository.delete_dossier(dossier)


@router.get(
    "/runs/{run_id}/pages/{page_id}/screenshot",
    summary="Image d'une page d'un run",
    description="Image de la page, sur laquelle dessiner les `boxes` des entités (coordonnées normalisées). Pour un "
    "run `persist=false` terminé, la capture est conservée avec le résultat et supprimée à son expiration "
    "(`expires_at`), avec lui. Le fichier d'origine, lui, est supprimé à la fin du run. Même scope strict que "
    "GET /api/ephemeral/runs/{id}.",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}, "description": "Capture de la page."},
        404: {"description": "Run ou page introuvable, pas de capture, ou run d'un autre créateur."},
    },
)
async def get_ephemeral_page_screenshot(
    run_id: uuid.UUID,
    page_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> Response:
    ephemeral_repository = EphemeralRepository(db)
    key: str | None = None
    if await ephemeral_repository.get_dossier_ephemere(run_id) is not None:
        dossier, _ = await _get_owned_run_or_404(db, run_id, identity)
        key = next(
            (
                page.screenshot_key
                for document in dossier.documents
                for page in document.pages
                if page.id == page_id and page.screenshot_key
            ),
            None,
        )
    else:
        result = await ephemeral_repository.get_result(run_id)
        if result is None or result.created_by != identity.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run éphémère introuvable")
        key = result.screenshot_keys.get(str(page_id))
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture introuvable")
    data, content_type = await run_in_threadpool(s3_connector.download, key)
    return Response(content=data, media_type=content_type)


def _parse_definitions[T](adapter: TypeAdapter[list[T]], raw: str, field: str) -> list[T]:
    """Les définitions arrivent en JSON dans un champ de formulaire multipart (un fichier et une liste d'objets
    ne tiennent pas dans un même corps JSON) : 422 si le JSON est invalide ou la liste vide."""
    try:
        definitions = adapter.validate_json(raw)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"`{field}` : JSON invalide ({error.errors()[0]['msg']})",
        ) from error
    if not definitions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"`{field}` ne peut pas être vide"
        )
    return definitions


async def _create_single_file_run(
    *,
    db: AsyncSession,
    identity: EphemeralIdentity,
    file: UploadFile,
    name: str,
    persist: bool,
    ttl_hours: int | None,
    multi_label: bool = False,
    classification_prompt: str = "",
    labels: list[LabelDefinitionIn] | None = None,
    extraction_prompt: str = "",
    entities: list[EntityDefinitionIn] | None = None,
) -> EphemeralRunCreated:
    """Analyse éphémère à une seule étape (classification OU extraction) + run sur un fichier, en un appel.
    Même cycle de vie que le flux B : `persist=false` purge dossier, fichier et analyse à la fin du run."""
    _reject_persist_for_env_key(identity, persist)
    ttl = _validate_ttl_hours(ttl_hours)
    analyse_repository = AnalyseRepository(db)
    analyse = await analyse_repository.create(name=name, description="", multi_label=multi_label)
    analyse = await analyse_repository.get(analyse.id)
    if labels:
        if classification_prompt:
            await analyse_repository.update_classification_prompt(analyse, classification_prompt)
        await analyse_repository.update_classification_labels(
            analyse, [LabelDefinition(name=lbl.name, definition=lbl.definition) for lbl in labels]
        )
    if entities:
        if extraction_prompt:
            await analyse_repository.update_extraction_prompt(analyse, extraction_prompt)
        await analyse_repository.update_extraction_entities(
            analyse,
            [EntityDefinition(name=ent.name, definition=ent.definition, type=ent.type) for ent in entities],
        )
    await EphemeralRepository(db).create_analyse_ephemere(
        analyse_id=analyse.id, persist=persist, created_by=identity.id
    )
    dossier = await _create_run(
        db=db,
        identity=identity,
        analyse=analyse,
        files=await _read_upload_files([file]),
        persist=persist,
        ttl_hours=ttl,
        name=name,
    )
    return EphemeralRunCreated(run_id=dossier.id)


@router.post(
    "/classifications",
    response_model=EphemeralRunCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Classe les pages d'un document en un seul appel",
    description='Multipart : `file` (un document), `labels` (JSON : `[{"name": "CNI", "definition": "..."}]`, '
    "au moins un), `multi_label` (défaut false : un seul label par page ; true : un ou plusieurs), "
    "`classification_prompt` (optionnel), `persist` (défaut false). Crée l'analyse et lance le run "
    "immédiatement (seule la classification est exécutée) ; lisez le résultat avec "
    "GET /api/ephemeral/classifications/{run_id}. TTL et purge : voir docs/ephemeral-api.md.",
    responses={
        400: {"description": "ttl_hours hors bornes (doit être entre 1 et 17520)."},
        422: {"description": "`labels` n'est pas un JSON valide ou est vide."},
    },
)
async def create_ephemeral_classification(
    file: UploadFile,
    labels: Annotated[str, Form(description='JSON : [{"name": "...", "definition": "..."}]')],
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
    multi_label: Annotated[bool, Form()] = False,
    classification_prompt: Annotated[str, Form()] = "",
    persist: Annotated[bool, Form()] = False,
    ttl_hours: Annotated[int | None, Query()] = None,
) -> EphemeralRunCreated:
    return await _create_single_file_run(
        db=db,
        identity=identity,
        file=file,
        name=f"Classification éphémère {uuid.uuid4()}",
        persist=persist,
        ttl_hours=ttl_hours,
        multi_label=multi_label,
        classification_prompt=classification_prompt,
        labels=_parse_definitions(TypeAdapter(list[LabelDefinitionIn]), labels, "labels"),
    )


@router.post(
    "/classification-and-extraction",
    response_model=EphemeralRunCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Classe les pages et extrait les entités d'un document en un seul appel",
    description='Multipart : `file` (un document), `labels` (JSON : `[{"name": "CNI", "definition": "..."}]`, au moins '
    'un), `entities` (JSON : `[{"name": "nom", "definition": "...", "type": "texte"}]`, au moins une), `multi_label`, '
    "`classification_prompt` et `extraction_prompt` (optionnels), `persist` (défaut false). **Un seul run** : le "
    "fichier n'est envoyé et traité qu'une fois (texte, captures), puis classification et extraction tournent en "
    "parallèle. Lisez les deux résultats avec le même `run_id` : GET /api/ephemeral/classifications/{run_id} et "
    "GET /api/ephemeral/extractions/{run_id}. TTL et purge : voir docs/ephemeral-api.md.",
    responses={
        400: {"description": "ttl_hours hors bornes (doit être entre 1 et 17520)."},
        422: {"description": "`labels` ou `entities` n'est pas un JSON valide ou est vide."},
    },
)
async def create_ephemeral_classification_and_extraction(
    file: UploadFile,
    labels: Annotated[str, Form(description='JSON : [{"name": "...", "definition": "..."}]')],
    entities: Annotated[str, Form(description='JSON : [{"name": "...", "definition": "...", "type": "texte"}]')],
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
    multi_label: Annotated[bool, Form()] = False,
    classification_prompt: Annotated[str, Form()] = "",
    extraction_prompt: Annotated[str, Form()] = "",
    persist: Annotated[bool, Form()] = False,
    ttl_hours: Annotated[int | None, Query()] = None,
) -> EphemeralRunCreated:
    return await _create_single_file_run(
        db=db,
        identity=identity,
        file=file,
        name=f"{COMBINED_RUN_PREFIX} éphémères {uuid.uuid4()}",
        persist=persist,
        ttl_hours=ttl_hours,
        multi_label=multi_label,
        classification_prompt=classification_prompt,
        labels=_parse_definitions(TypeAdapter(list[LabelDefinitionIn]), labels, "labels"),
        extraction_prompt=extraction_prompt,
        entities=_parse_definitions(TypeAdapter(list[EntityDefinitionIn]), entities, "entities"),
    )


@router.get(
    "/classifications/{run_id}",
    response_model=EphemeralClassificationOut,
    summary="Résultat d'une classification : le ou les labels de chaque page",
    description="`status` indique l'avancement (en_attente/en_cours/terminé/échec) ; les `labels` des pages "
    "se remplissent au fil du run. Même scope strict que GET /api/ephemeral/runs/{id}.",
    responses={404: {"description": "Run introuvable, pas éphémère, ou appartenant à un autre créateur."}},
)
async def get_ephemeral_classification(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> EphemeralClassificationOut:
    return to_classification_out(await _get_run_out_or_404(db, run_id, identity))


@router.post(
    "/extractions",
    response_model=EphemeralRunCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Extrait les entités d'un document en un seul appel",
    description='Multipart : `file` (un document), `entities` (JSON : `[{"name": "nom", "definition": '
    '"...", "type": "texte"}]`, au moins une), `extraction_prompt` (optionnel), `persist` (défaut false). '
    "Même fonctionnement que POST /api/ephemeral/classifications ; résultat via "
    "GET /api/ephemeral/extractions/{run_id}.",
    responses={
        400: {"description": "ttl_hours hors bornes (doit être entre 1 et 17520)."},
        422: {"description": "`entities` n'est pas un JSON valide ou est vide."},
    },
)
async def create_ephemeral_extraction(
    file: UploadFile,
    entities: Annotated[str, Form(description='JSON : [{"name": "...", "definition": "...", "type": "texte"}]')],
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
    extraction_prompt: Annotated[str, Form()] = "",
    persist: Annotated[bool, Form()] = False,
    ttl_hours: Annotated[int | None, Query()] = None,
) -> EphemeralRunCreated:
    return await _create_single_file_run(
        db=db,
        identity=identity,
        file=file,
        name=f"Extraction éphémère {uuid.uuid4()}",
        persist=persist,
        ttl_hours=ttl_hours,
        extraction_prompt=extraction_prompt,
        entities=_parse_definitions(TypeAdapter(list[EntityDefinitionIn]), entities, "entities"),
    )


@router.get(
    "/extractions/{run_id}",
    response_model=EphemeralExtractionOut,
    summary="Résultat d'une extraction : les entités de chaque page",
    description="Chaque page liste les entités qui la couvrent (une entité sur plusieurs pages apparaît sur "
    "chacune, avec `pages` = toutes ses pages). Même scope strict que GET /api/ephemeral/runs/{id}.",
    responses={404: {"description": "Run introuvable, pas éphémère, ou appartenant à un autre créateur."}},
)
async def get_ephemeral_extraction(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> EphemeralExtractionOut:
    return to_extraction_out(await _get_run_out_or_404(db, run_id, identity))


# --- Verdicts et métriques ---


async def _run_metrics_or_404(db: AsyncSession, run_id: uuid.UUID, identity: EphemeralIdentity) -> EphemeralRunMetrics:
    """Le condensé non sensible du run (voir EphemeralRunMetrics), à jour. Un run encore en base (en cours, ou
    persist=true) est condensé à la demande ; un run terminé persist=false a son condensé depuis sa finalisation, et
    il reste lisible après la purge de son résultat. 404 si le run n'existe pas ou n'est pas à l'appelant."""
    repository = EphemeralRepository(db)
    if await repository.get_dossier_ephemere(run_id) is not None:
        dossier, record = await _get_owned_run_or_404(db, run_id, identity)
        digest = ephemeral_metrics.build_digest(to_run_schema(dossier, record))
        return await repository.save_run_metrics(run_id=run_id, created_by=identity.id, digest=digest)
    stored = await repository.get_run_metrics(run_id)
    if stored is not None and stored.created_by == identity.id:
        return stored
    result = await repository.get_result(run_id)
    if result is not None and result.created_by == identity.id:
        # Résultat conservé avant l'existence des condensés : on le condense maintenant, tant qu'il est lisible.
        digest = ephemeral_metrics.build_digest(EphemeralRunOut.model_validate(result.payload))
        return await repository.save_run_metrics(run_id=run_id, created_by=identity.id, digest=digest)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run éphémère introuvable")


def _feedback_out(row) -> FeedbackOut:
    return FeedbackOut(
        prediction_id=row.prediction_id,
        kind=row.kind,
        name=row.name,
        source=row.source,
        page_number=row.page_number,
        confidence=row.confidence,
        verdict=row.verdict,
        expected_name=row.expected_name,
    )


@router.post(
    "/runs/{run_id}/feedback",
    response_model=list[FeedbackOut],
    summary="Dit si des prédictions du run sont bonnes ou mauvaises",
    description="Un verdict par prédiction : `correct` ou `incorrect` (avec, pour un label, le `expected_name` "
    "attendu). Les `prediction_id` se lisent dans GET .../classifications/{run_id}, GET .../extractions/{run_id} ou "
    "`predictions[].id` de GET .../runs/{run_id}. Un nouveau verdict sur la même prédiction remplace le précédent. "
    "Seuls la méthode, le nom, la confiance et la page sont gardés pour les métriques : jamais la valeur extraite. "
    "Possible tant que le run existe, y compris après la purge de son résultat (le condensé est conservé "
    "EPHEMERAL_METRICS_RETENTION_DAYS jours).",
    responses={
        404: {"description": "Run introuvable ou appartenant à un autre appelant."},
        422: {"description": "`prediction_id` inconnu pour ce run, ou `expected_name` sur autre chose qu'un label."},
    },
)
async def post_ephemeral_feedback(
    run_id: uuid.UUID,
    body: FeedbackIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> list[FeedbackOut]:
    digest = await _run_metrics_or_404(db, run_id, identity)
    known = {p["id"]: p for p in digest.predictions}
    unknown = sorted({str(item.prediction_id) for item in body.items if str(item.prediction_id) not in known})
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"prediction_id inconnus pour ce run : {unknown}"
        )
    for item in body.items:
        if item.expected_name is not None and known[str(item.prediction_id)]["kind"] != PredictionKind.LABEL.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="`expected_name` ne s'applique qu'à un label (pas à une entité)",
            )
    repository = EphemeralRepository(db)
    rows = [
        await repository.upsert_feedback(
            run_id=run_id,
            created_by=identity.id,
            prediction=known[str(item.prediction_id)],
            verdict=item.verdict,
            expected_name=item.expected_name,
        )
        for item in body.items
    ]
    await db.commit()
    return [_feedback_out(row) for row in rows]


@router.get(
    "/runs/{run_id}/feedback",
    response_model=list[FeedbackOut],
    summary="Les verdicts déjà donnés sur ce run",
    responses={404: {"description": "Run introuvable ou appartenant à un autre appelant."}},
)
async def list_ephemeral_feedback(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> list[FeedbackOut]:
    await _run_metrics_or_404(db, run_id, identity)
    rows = await EphemeralRepository(db).list_feedback(identity.id, run_id=run_id)
    return [_feedback_out(row) for row in rows]


@router.get(
    "/runs/{run_id}/metrics",
    response_model=RunMetricsOut,
    summary="Métriques d'un run : volumes, confiances, accord entre méthodes, qualité jugée",
    description="Calculées sur le condensé non sensible du run (jamais sur son contenu) : durée, nombre de pages, "
    "prédictions et confiance par méthode (`source`) et par nom, accord textuel/visuel de la classification, et, si "
    "des verdicts ont été donnés, la précision par méthode et la matrice de confusion. Lisible même après la purge "
    "du résultat du run.",
    responses={404: {"description": "Run introuvable ou appartenant à un autre appelant."}},
)
async def get_ephemeral_run_metrics(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> RunMetricsOut:
    digest = await _run_metrics_or_404(db, run_id, identity)
    feedback = await EphemeralRepository(db).list_feedback(identity.id, run_id=run_id)
    return ephemeral_metrics.run_metrics(digest, feedback)


@router.delete(
    "/runs/{run_id}/metrics",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprime le condensé et les verdicts d'un run",
    description="Sans effet sur le run lui-même. Les métriques de ce run disparaissent de GET /metrics.",
    responses={404: {"description": "Rien à supprimer pour ce run (ou il appartient à un autre appelant)."}},
)
async def delete_ephemeral_run_metrics(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
) -> None:
    if not await EphemeralRepository(db).delete_run_metrics_and_feedback(run_id, identity.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucune métrique pour ce run")


@router.get(
    "/metrics",
    response_model=GlobalMetricsOut,
    summary="Métriques de tous vos runs : précision par méthode et par label/entité, confusions, accord",
    description="Agrège les verdicts et les condensés de l'appelant (une clé d'API ou un compte ne voit que les "
    "siens). Filtres : `kind` (label/entity), `source` (textual/visual/gliner), `since` (date ISO).",
)
async def get_ephemeral_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[EphemeralIdentity, Depends(get_ephemeral_identity)],
    kind: Annotated[PredictionKind | None, Query()] = None,
    source: Annotated[PredictionSource | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
) -> GlobalMetricsOut:
    repository = EphemeralRepository(db)
    feedback = await repository.list_feedback(identity.id, kind=kind, source=source, since=since)
    digests = await repository.list_run_metrics(identity.id, since=since)
    return ephemeral_metrics.global_metrics(digests, feedback)
