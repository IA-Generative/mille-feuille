import asyncio
import contextlib
import time
import uuid
from typing import Any, Protocol

from loguru import logger
from mic_worker import S3Client
from mic_worker.typed import AsyncProgressProtocol, AsyncTaskInterface, IncomingMessage
from millefeuille.exceptions import NotFoundError
from millefeuille.exceptions import ValidationError as MilleFeuilleValidationError
from millefeuille.models import DossierStatus, ExecutionStepStatus
from millefeuille_ephemeral import EphemeralClient, EphemeralRun, MilleFeuilleError
from pydantic import ValidationError

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

_PROGRESS_VALIDATED = 0.05
_PROGRESS_FILES_READY = 0.2
_PROGRESS_RUN_STARTED = 0.25
_PROGRESS_RUN_MAX = 0.95  # 1.0 est le message terminal : jamais émis en progression

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
            if result.status != DossierStatus.TERMINE:
                raise RunFailedError(self._failure_message(result))
            response = self._to_response(result)
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
                self.client.runs.create, analyse_id, files, PERSIST_PLATEFORME, request.ttl_hours
            )
        except NotFoundError as error:
            if request.analyse_id is None:
                raise  # l'analyse vient d'être créée : un 404 ici est un incident amont, pas une faute du consommateur
            raise AnalysisNotFoundError(
                f"L'analyse {request.analyse_id} est introuvable, ou hors du périmètre du jeton du worker."
            ) from error

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
                raise RunTimeoutError(f"Le run {run_id} n'est pas terminé après {self.run_timeout:.0f} s.")
            await asyncio.sleep(self.poll_interval)

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

    @staticmethod
    def _to_response(run: EphemeralRun) -> dict[str, Any]:
        """Résultat complet du run ; les clés S3 internes de mille-feuille n'ont pas d'intérêt pour le consommateur."""
        return run.model_dump(mode="json", exclude={"documents": {"__all__": {"s3_key"}}})

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
