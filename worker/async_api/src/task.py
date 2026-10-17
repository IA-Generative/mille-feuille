import asyncio
import contextlib
import json
import time
import uuid
from typing import Any, Protocol

from loguru import logger
from mic_worker import S3Client
from mic_worker.typed import AsyncProgressProtocol, AsyncTaskInterface, IncomingMessage
from millefeuille.exceptions import NotFoundError
from millefeuille.exceptions import ValidationError as MilleFeuilleValidationError
from millefeuille.models import DossierStatus, ExecutionStepStatus, PredictionKind
from millefeuille_ephemeral import EphemeralClient, EphemeralRun, MilleFeuilleError
from pydantic import ValidationError

from src.config import NOM_FICHIER_RESULTAT, REPONSE_MAX_OCTETS, SORTIE_AGENT_MAX_OCTETS
from src.enums import ClasseErreurAmont, EtatRun
from src.exceptions import (
    ECHEC_TECHNIQUE,
    AnalysisNotFoundError,
    FichierIntrouvableError,
    FileTooLargeError,
    InvalidRequestError,
    MilleFeuilleBridgeError,
    RunFailedError,
    RunTimeoutError,
    TooManyFilesError,
    UpstreamError,
)
from src.messages import PERSIST_PLATEFORME, AnalyzeRequest
from src.metriques import (
    PAGES_TOTAL,
    RESULTAT_OCTETS,
    RUN_DURATION_SECONDS,
    RUN_WAIT_SECONDS,
    RUNS_TOTAL,
    UPSTREAM_ERRORS_TOTAL,
)
from src.schemas import (
    AgentResume,
    DocumentResume,
    Durees,
    EntiteResume,
    LabelResume,
    MilleFeuilleResult,
    PageResume,
)

_PROGRESS_VALIDATED = 0.05
_PROGRESS_FILES_READY = 0.2
_PROGRESS_RUN_STARTED = 0.25
_PROGRESS_RUN_MAX = 0.95  # 1.0 est le message terminal : jamais émis en progression

_PREMIER_STATUT_SERVEUR = 500

# Libellés neutres rendus au consommateur pour une erreur du service d'analyse (garde C-17).
_LIBELLE_REQUETE_REFUSEE = "Requête refusée par le service d'analyse"
_LIBELLE_AMONT_INDISPONIBLE = "Service d'analyse indisponible, réessayer plus tard"


class _Clock(Protocol):
    def __call__(self) -> float: ...


class AnalyzeTask(AsyncTaskInterface):
    """Exécute une analyse mille-feuille pour une tâche AsyncTaskAPI, via l'API éphémère.

    1. valide le message et borne la taille des fichiers (HEAD S3, avant tout téléchargement) ;
    2. télécharge les fichiers depuis S3 ;
    3. crée l'analyse éphémère si besoin, lance le run et attend sa fin en publiant la progression
       (étapes d'exécution terminées / total) ;
    4. renvoie le résultat du run, puis supprime le résultat conservé côté mille-feuille.

    Le SDK est synchrone : ses appels tournent dans un thread pour ne pas bloquer la boucle asyncio.
    """

    def __init__(
        self,
        s3_client: S3Client,
        client: EphemeralClient,
        *,
        client_depot: EphemeralClient | None = None,
        max_file_size: int,
        max_total_size: int,
        max_files: int,
        run_timeout: float,
        poll_interval: float,
        delete_run_after_result: bool = True,
        clock: _Clock = time.monotonic,
    ) -> None:
        self.s3_client = s3_client
        self.client = client
        # Le client du dépôt multipart a un délai plus long (`MILLEFEUILLE_UPLOAD_TIMEOUT`) ; sans lui, le même.
        self.client_depot = client_depot or client
        self.max_file_size = max_file_size
        self.max_total_size = max_total_size
        self.max_files = max_files
        self.run_timeout = run_timeout
        self.poll_interval = poll_interval
        self.delete_run_after_result = delete_run_after_result
        self._clock = clock

    async def execute(self, incoming_message: IncomingMessage, progress: AsyncProgressProtocol) -> dict[str, Any]:
        task_id = incoming_message.task_id
        with logger.contextualize(task_id=task_id):
            try:
                return await self._executer(incoming_message, progress)
            except MilleFeuilleBridgeError as e:
                logger.info(f"Task {task_id} failed [{e.error_code}]: {e.detail}")
                raise RuntimeError(f"{e.error_code}: {e.detail}") from e
            except MilleFeuilleError as e:
                erreur = self._traduire(e)
                UPSTREAM_ERRORS_TOTAL.labels(classe=self._classe_amont(e).value).inc()
                logger.error(
                    f"Task {task_id}: mille-feuille error [{erreur.error_code}] — "
                    f"{type(e).__name__} {e.status_code} {e.message}"
                )
                raise RuntimeError(f"{erreur.error_code}: {erreur.detail}") from e
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(f"Task {task_id}: échec technique — {type(exc).__name__}: {exc}")
                raise RuntimeError(ECHEC_TECHNIQUE) from exc

    @staticmethod
    def _classe_amont(erreur: MilleFeuilleError) -> ClasseErreurAmont:
        if erreur.status_code is None:
            return ClasseErreurAmont.RESEAU
        return (
            ClasseErreurAmont.CINQ_CENTS
            if erreur.status_code >= _PREMIER_STATUT_SERVEUR
            else ClasseErreurAmont.QUATRE_CENTS
        )

    @staticmethod
    def _traduire(erreur: MilleFeuilleError) -> MilleFeuilleBridgeError:
        """Une erreur du backend, en code neutre : le consommateur n'en voit ni l'URL, ni le statut,
        ni le texte brut. Un 400/422 est de son ressort (la requête est refusée) ; tout le reste
        (authentification du worker, 5xx, réseau) est un incident amont, à réessayer."""
        if isinstance(erreur, MilleFeuilleValidationError):
            return InvalidRequestError(_LIBELLE_REQUETE_REFUSEE)
        return UpstreamError(_LIBELLE_AMONT_INDISPONIBLE)

    async def _executer(self, incoming_message: IncomingMessage, progress: AsyncProgressProtocol) -> dict[str, Any]:
        task_id = incoming_message.task_id
        request = self._parse(incoming_message.body)
        client_id = self._client_id(request)
        await progress(progress=_PROGRESS_VALIDATED, payload=None)

        await self._check_sizes(request)
        files = await self._download(task_id, request)
        await progress(progress=_PROGRESS_FILES_READY, payload=None)

        created_analyse_id: uuid.UUID | None = None
        run_id: uuid.UUID | None = None
        try:
            if request.analysis is not None:
                analyse = await asyncio.to_thread(
                    self.client.analyses.create_from_config, request.analysis.vers_config()
                )
                created_analyse_id = analyse.id
                analyse_id = analyse.id
            else:
                assert request.analyse_id is not None
                analyse_id = request.analyse_id
            run = await self._creer_run(request, analyse_id, files)
            run_id = run.id
            logger.info(f"Task {task_id}: run {run_id} started")
            await progress(progress=_PROGRESS_RUN_STARTED, payload=None)

            result = await self._wait(run_id, progress)
            self._observer(result)
            if result.status != DossierStatus.TERMINE:
                raise RunFailedError(self._failure_message(result))
            resultat_file_id, octets = await self._deposer_resultat(client_id, task_id, result)
            response = self._to_response(result, resultat_file_id, octets)
            if self.delete_run_after_result:
                await self._delete_run_quietly(task_id, run_id)
            return response
        except BaseException:
            # Échec, erreur amont, délai dépassé ou arrêt du worker (CancelledError) : ne pas laisser
            # un run orphelin. La traduction en code neutre est faite un étage plus haut.
            self._abandon(task_id, run_id, created_analyse_id)
            raise

    async def _creer_run(
        self, request: AnalyzeRequest, analyse_id: uuid.UUID, files: list[tuple[str, bytes]]
    ) -> EphemeralRun:
        try:
            return await asyncio.to_thread(
                self.client_depot.runs.create, analyse_id, files, PERSIST_PLATEFORME, request.ttl_hours
            )
        except NotFoundError as error:
            if request.analyse_id is None:
                raise  # l'analyse vient d'être créée : un 404 ici est un incident amont, pas une faute du consommateur
            raise AnalysisNotFoundError(
                f"L'analyse {request.analyse_id} est introuvable, ou hors du périmètre du jeton du worker."
            ) from error

    @staticmethod
    def _client_id(request: AnalyzeRequest) -> str:
        """Le client propriétaire des fichiers (`{client_id}/{uuid}/{nom}`), qui recevra le résultat
        sous son préfixe. Tous les fichiers doivent partager ce préfixe : l'API l'a déjà vérifié pour
        chacun, le worker refuse ce qui lui parviendrait autrement."""
        prefixes = {ref.file_id.split("/", 1)[0] for ref in request.files}
        if len(prefixes) != 1 or "" in prefixes:
            raise InvalidRequestError("Les fichiers doivent tous appartenir au même client.")
        return prefixes.pop()

    def _parse(self, body: dict[str, Any]) -> AnalyzeRequest:
        try:
            request = AnalyzeRequest.model_validate(body)
        except ValidationError as error:
            details = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'message'} : {e['msg']}" for e in error.errors())
            raise InvalidRequestError(f"Message d'entrée invalide — {details}") from error
        if len(request.files) > self.max_files:
            raise TooManyFilesError(f"Trop de fichiers : {len(request.files)} (maximum {self.max_files}).")
        return request

    async def _check_sizes(self, request: AnalyzeRequest) -> None:
        """Borne la mémoire AVANT de charger quoi que ce soit : un fichier trop gros tuerait le pod (OOM)
        et le message serait redélivré indéfiniment."""
        total = 0
        for ref in request.files:
            try:
                size = await self.s3_client.get_size(ref.file_id)
            except FileNotFoundError as error:
                raise FichierIntrouvableError(f"Le fichier {ref.display_name} est introuvable au stockage.") from error
            if size > self.max_file_size:
                raise FileTooLargeError(
                    f"Le fichier {ref.display_name} pèse {size} octets, maximum {self.max_file_size}."
                )
            total += size
        if total > self.max_total_size:
            raise FileTooLargeError(f"Les fichiers pèsent {total} octets au total, maximum {self.max_total_size}.")

    async def _download(self, task_id: str, request: AnalyzeRequest) -> list[tuple[str, bytes]]:
        files: list[tuple[str, bytes]] = []
        for ref in request.files:
            logger.info(f"Task {task_id}: downloading {ref.file_id}")
            files.append((ref.display_name, await self.s3_client.download(ref.file_id)))
        return files

    async def _wait(self, run_id: uuid.UUID, progress: AsyncProgressProtocol) -> EphemeralRun:
        deadline = self._clock() + self.run_timeout
        last_reported = _PROGRESS_RUN_STARTED
        while True:
            run = await asyncio.to_thread(self.client.runs.get, run_id)
            if run.status.is_terminal:
                return run
            reported = self._progress_of(run)
            if reported > last_reported:
                last_reported = reported
                await progress(progress=reported, payload=None)
            if self._clock() + self.poll_interval > deadline:
                RUNS_TOTAL.labels(etat=EtatRun.DELAI.value).inc()
                raise RunTimeoutError(f"Le run {run_id} n'est pas terminé après {self.run_timeout:.0f} s.")
            await asyncio.sleep(self.poll_interval)

    @staticmethod
    def _observer(run: EphemeralRun) -> None:
        """Les métriques d'un run conclu : son issue, sa durée, son attente avant la première étape, ses pages."""
        etat = {DossierStatus.TERMINE: EtatRun.TERMINE, DossierStatus.ARRETE: EtatRun.ARRETE}.get(
            run.status, EtatRun.ECHEC
        )
        RUNS_TOTAL.labels(etat=etat.value).inc()
        if run.ended_at is not None:
            RUN_DURATION_SECONDS.observe(max(0.0, (run.ended_at - run.created_at).total_seconds()))
        debuts = [step.started_at for step in run.execution_steps]
        if debuts:
            RUN_WAIT_SECONDS.observe(max(0.0, (min(debuts) - run.created_at).total_seconds()))
        if run.status == DossierStatus.TERMINE:
            PAGES_TOTAL.inc(sum(len(document.pages) for document in run.documents))

    @staticmethod
    def _progress_of(run: EphemeralRun) -> float:
        steps = run.execution_steps
        if not steps:
            return _PROGRESS_RUN_STARTED
        done = sum(1 for step in steps if step.status != ExecutionStepStatus.EN_COURS)
        return _PROGRESS_RUN_STARTED + (_PROGRESS_RUN_MAX - _PROGRESS_RUN_STARTED) * done / len(steps)

    @staticmethod
    def _failure_message(run: EphemeralRun) -> str:
        """Ce que le consommateur apprend d'un run en échec : son état et les étapes concernées, par
        leur libellé (les noms d'agents qu'il a lui-même définis). La sortie des étapes — texte produit
        par un modèle, potentiellement long et parlant — reste au journal (garde C-17)."""
        failed = [step for step in run.execution_steps if step.status == ExecutionStepStatus.ECHEC]
        for step in failed:
            logger.warning(f"Run {run.id}: étape `{step.label}` en échec — {step.output or 'sans détail'}")
        etapes = ", ".join(step.label for step in failed)
        return f"Le run est {run.status.value}" + (f" — étapes en échec : {etapes}" if etapes else ".")

    async def _deposer_resultat(self, client_id: str, task_id: str, run: EphemeralRun) -> tuple[str, int]:
        """Le run complet, en JSON, sur le stockage d'async-api sous le préfixe du client. Clé
        déterministe : une redélivrance réécrit la même, c'est ce qui rend la tâche rejouable."""
        charge = json.dumps(
            run.model_dump(mode="json", exclude={"documents": {"__all__": {"s3_key"}}}),
            ensure_ascii=False,
        ).encode("utf-8")
        cle = f"{client_id}/{task_id}/{NOM_FICHIER_RESULTAT}"
        await asyncio.to_thread(self.s3_client.upload, cle, charge)
        RESULTAT_OCTETS.observe(len(charge))
        return cle, len(charge)

    @classmethod
    def _to_response(cls, run: EphemeralRun, resultat_file_id: str, octets: int) -> dict[str, Any]:
        """Le résumé borné du run : catégories par page, entités par document, sortie des agents."""
        resume = MilleFeuilleResult(
            status=run.status.value,
            run_id=str(run.id),
            resultat_file_id=resultat_file_id,
            resultat_octets=octets,
            documents=[cls._resumer_document(document) for document in run.documents],
            agents=[cls._resumer_agent(step) for step in run.execution_steps],
            durees=Durees(created_at=run.created_at, started_at=run.started_at, ended_at=run.ended_at),
        )
        return cls._borner(resume).model_dump(mode="json")

    @staticmethod
    def _resumer_document(document: Any) -> DocumentResume:  # noqa: ANN401 — millefeuille.models.Document
        pages = [
            PageResume(
                page_number=page.page_number,
                labels=[
                    LabelResume(name=p.name, confidence=p.confidence, source=p.source.value)
                    for p in page.predictions
                    if p.kind == PredictionKind.LABEL
                ],
            )
            for page in document.pages
        ]
        entites: dict[tuple[str, str, str], EntiteResume] = {}
        for page in document.pages:
            for p in page.predictions:
                if p.kind != PredictionKind.ENTITY:
                    continue
                cle = (p.name, p.value, p.source.value)
                entite = entites.setdefault(
                    cle,
                    EntiteResume(name=p.name, value=p.value, confidence=p.confidence, source=p.source.value, pages=[]),
                )
                if page.page_number not in entite.pages:
                    entite.pages.append(page.page_number)
        return DocumentResume(
            name=document.name, page_count=len(document.pages), pages=pages, entities=list(entites.values())
        )

    @staticmethod
    def _resumer_agent(step: Any) -> AgentResume:  # noqa: ANN401 — millefeuille.models.ExecutionStep
        sortie = step.output
        tronque = sortie is not None and len(sortie.encode("utf-8")) > SORTIE_AGENT_MAX_OCTETS
        if tronque:
            sortie = sortie.encode("utf-8")[:SORTIE_AGENT_MAX_OCTETS].decode("utf-8", errors="ignore")
        return AgentResume(label=step.label, status=step.status.value, output=sortie, tronque=tronque)

    @staticmethod
    def _borner(resume: MilleFeuilleResult) -> MilleFeuilleResult:
        """Sous `REPONSE_MAX_OCTETS` : d'abord les entités (par moitiés), puis les pages. Le fichier
        déposé garde tout ; le résumé le dit (`tronque`)."""

        def taille() -> int:
            return len(resume.model_dump_json().encode("utf-8"))

        while taille() > REPONSE_MAX_OCTETS and any(document.entities for document in resume.documents):
            for document in resume.documents:
                document.entities = document.entities[: len(document.entities) // 2]
            resume.tronque = True
        while taille() > REPONSE_MAX_OCTETS and any(document.pages for document in resume.documents):
            for document in resume.documents:
                document.pages = document.pages[: len(document.pages) // 2]
            resume.tronque = True
        return resume

    async def _delete_run_quietly(self, task_id: str, run_id: uuid.UUID) -> None:
        try:
            await asyncio.to_thread(self.client.runs.delete, run_id)
        except MilleFeuilleError as error:
            # Le résultat est déjà dans la réponse : au pire, il expire tout seul au TTL.
            logger.warning(f"Task {task_id}: could not delete run {run_id} — {error.message}")

    def _abandon(self, task_id: str, run_id: uuid.UUID | None, created_analyse_id: uuid.UUID | None) -> None:
        """Nettoyage au mieux, synchrone à dessein : il doit aussi s'exécuter quand la tâche est annulée."""
        with contextlib.suppress(MilleFeuilleError):
            if run_id is not None:
                self.client.runs.stop(run_id)
                self.client.runs.delete(run_id)
        with contextlib.suppress(MilleFeuilleError):
            if created_analyse_id is not None:
                self.client.analyses.delete(created_analyse_id)
        logger.info(f"Task {task_id}: cleanup done (run={run_id}, analyse={created_analyse_id})")
