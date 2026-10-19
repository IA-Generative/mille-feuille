import asyncio
import json
import threading
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from contract import example
from mic_worker import S3Client
from mic_worker.typed import IncomingMessage
from millefeuille.exceptions import AuthenticationError, ConnectionFailedError, NotFoundError, ServerError
from millefeuille.exceptions import ValidationError as MilleFeuilleValidationError
from millefeuille_ephemeral import EphemeralClient, EphemeralRun

from src.task import AnalyzeTask

RUN_ID = "3f2b8c1e-5d4a-4e6b-9a7c-1d2e3f4a5b6c"
ANALYSE_ID = "9a1b2c3d-0000-4000-8000-000000000001"
ANALYSIS = {"name": "Vérification CNI", "classification_prompt": "Classe", "labels": [{"name": "CNI"}]}
BODY = {"analysis": ANALYSIS, "files": [{"file_id": "astree/a1/cni.pdf"}], "ttl_hours": 48}


def make_run(status: str = "terminé", step_statuses: tuple[str, ...] = ("terminé",)) -> EphemeralRun:
    payload = example("EphemeralRunOut", id=RUN_ID, status=status, ttl_hours=48, expires_at=None)
    step = payload["execution_steps"][0]
    payload["execution_steps"] = [{**step, "status": s, "output": f"sortie {i}"} for i, s in enumerate(step_statuses)]
    return EphemeralRun.model_validate(payload)


def make_analyse_id_holder() -> MagicMock:
    holder = MagicMock()
    holder.id = uuid.UUID(ANALYSE_ID)
    return holder


def make_task(
    runs: list[EphemeralRun],
    *,
    file_size: int = 10,
    clock: Any = None,
    run_timeout: float = 100.0,
    poll_interval: float = 0,
    **kwargs: Any,
) -> tuple[AnalyzeTask, MagicMock, MagicMock]:
    s3 = MagicMock(spec=S3Client)
    s3.get_size = AsyncMock(return_value=file_size)
    s3.download = AsyncMock(return_value=b"%PDF")
    client = MagicMock(spec=EphemeralClient)
    client.analyses = MagicMock()
    client.analyses.create_from_config.return_value = make_analyse_id_holder()
    client.runs = MagicMock()
    client.runs.create.return_value = make_run("en_cours", ("en_cours",))
    client.runs.get.side_effect = runs
    task = AnalyzeTask(
        s3,
        client,
        max_file_size=1000,
        max_total_size=1500,
        max_files=3,
        run_timeout=run_timeout,
        poll_interval=poll_interval,
        **({"clock": clock} if clock else {}),
        **kwargs,
    )
    return task, s3, client


def message(body: dict[str, Any] | None = None) -> IncomingMessage:
    return IncomingMessage(task_id="task-1", body=BODY if body is None else body)


async def run_task(task: AnalyzeTask, body: dict[str, Any] | None = None) -> tuple[dict[str, Any], AsyncMock]:
    progress = AsyncMock()
    return await task.execute(message(body), progress), progress


async def test_success_creates_analysis_runs_waits_and_cleans_up() -> None:
    task, s3, client = make_task([make_run("en_cours", ("terminé", "en_cours")), make_run("terminé", ("terminé",))])

    response, progress = await run_task(task)

    client.analyses.create_from_config.assert_called_once()
    client.runs.create.assert_called_once_with(uuid.UUID(ANALYSE_ID), [("cni.pdf", b"%PDF")], False, 48)
    s3.download.assert_awaited_once_with("astree/a1/cni.pdf")
    assert response["status"] == "terminé" and response["run_id"] == RUN_ID
    assert response["agents"][0] == {"label": "texte", "status": "terminé", "output": "sortie 0", "tronque": False}
    assert response["resultat_file_id"] == "astree/task-1/resultat.json"
    assert response["tronque"] is False
    client.runs.delete.assert_called_once_with(uuid.UUID(RUN_ID))
    client.analyses.delete.assert_not_called()
    values = [call.kwargs["progress"] for call in progress.await_args_list]
    assert values == sorted(values) and values[0] == 0.05 and max(values) < 1.0


async def test_upload_goes_through_the_dedicated_client_when_given() -> None:
    task, _, client = make_task([make_run()])
    client_depot = MagicMock(spec=EphemeralClient)
    client_depot.runs = MagicMock()
    client_depot.runs.create.return_value = make_run("en_cours", ("en_cours",))
    task.client_depot = client_depot

    await run_task(task)

    client_depot.runs.create.assert_called_once()
    client.runs.create.assert_not_called()


async def test_existing_analyse_id_skips_analysis_creation() -> None:
    task, _, client = make_task([make_run()])

    await run_task(task, {"analyse_id": ANALYSE_ID, "files": BODY["files"]})

    client.analyses.create_from_config.assert_not_called()
    assert client.runs.create.call_args.args[0] == uuid.UUID(ANALYSE_ID)
    assert client.runs.create.call_args.args[3] == 24  # ttl par défaut


async def test_persist_is_refused_by_the_contract() -> None:
    task, _, client = make_task([make_run()])

    with pytest.raises(RuntimeError, match=r"^INVALID_REQUEST: .*persist"):
        await run_task(task, {**BODY, "persist": True})

    client.runs.create.assert_not_called()


async def test_analysis_is_created_without_persist_and_with_platform_tools() -> None:
    task, _, client = make_task([make_run()])
    body = {**BODY, "analysis": {**ANALYSIS, "agents": [{"name": "a", "prompt": "p", "tools": ["lecture_document"]}]}}

    await run_task(task, body)

    config = client.analyses.create_from_config.call_args.args[0]
    assert config.persist is False
    assert [outil.value for outil in config.agents[0].tools] == ["lecture_document"]
    assert client.runs.create.call_args.args[2] is False


async def test_delete_after_result_can_be_disabled() -> None:
    task, _, client = make_task([make_run()], delete_run_after_result=False)

    await run_task(task)

    client.runs.delete.assert_not_called()


async def test_delete_failure_does_not_fail_the_task() -> None:
    task, _, client = make_task([make_run()])
    client.runs.delete.side_effect = NotFoundError("déjà purgé", status_code=404)

    response, _ = await run_task(task)

    assert response["status"] == "terminé"


@pytest.mark.parametrize(
    "body",
    [
        {"files": BODY["files"]},
        {**BODY, "analyse_id": ANALYSE_ID},
        {"analysis": ANALYSIS, "files": []},
        {"analysis": ANALYSIS, "files": BODY["files"], "ttl_hours": 0},
        {"analysis": ANALYSIS, "files": BODY["files"], "inconnu": 1},
        {"analysis": {"name": "n", "agents": [{"name": "a", "prompt": ""}]}, "files": BODY["files"]},
        {
            "analysis": {"name": "n", "agents": [{"name": "a", "prompt": "p", "tools": ["recherche_web"]}]},
            "files": BODY["files"],
        },
        {"analysis": ANALYSIS, "files": BODY["files"], "ttl_hours": 169},
    ],
)
async def test_invalid_message_is_rejected_before_any_io(body: dict[str, Any]) -> None:
    task, s3, client = make_task([])

    with pytest.raises(RuntimeError, match=r"^INVALID_REQUEST: Message d'entrée invalide"):
        await run_task(task, body)

    s3.get_size.assert_not_called()
    client.runs.create.assert_not_called()


async def test_too_many_files() -> None:
    task, _, _ = make_task([])
    body = {**BODY, "files": [{"file_id": f"k/{i}.pdf"} for i in range(4)]}

    with pytest.raises(RuntimeError, match=r"^TOO_MANY_FILES: Trop de fichiers"):
        await run_task(task, body)


async def test_oversized_file_is_refused_before_download() -> None:
    task, s3, client = make_task([], file_size=1001)

    with pytest.raises(RuntimeError, match=r"^FILE_TOO_LARGE: .*cni.pdf"):
        await run_task(task)

    s3.download.assert_not_called()
    client.analyses.create_from_config.assert_not_called()


async def test_total_size_is_bounded() -> None:
    task, s3, _ = make_task([], file_size=800)
    body = {**BODY, "files": [{"file_id": "astree/a1/a.pdf"}, {"file_id": "astree/a1/b.pdf"}]}

    with pytest.raises(RuntimeError, match=r"^FILE_TOO_LARGE: .*au total"):
        await run_task(task, body)

    s3.download.assert_not_called()


async def test_failed_run_reports_failing_steps_and_cleans_up() -> None:
    task, _, client = make_task([make_run("échec", ("terminé", "échec"))])

    with pytest.raises(RuntimeError, match=r"^RUN_FAILED: Le run est échec — étapes en échec : ") as exc:
        await run_task(task)

    assert "sortie 1" not in str(exc.value)  # la sortie d'une étape (texte d'un modèle) reste au journal
    client.runs.stop.assert_called_once()
    client.runs.delete.assert_called_once()
    client.analyses.delete.assert_called_once_with(uuid.UUID(ANALYSE_ID))


async def test_stopped_run_without_failed_step() -> None:
    task, _, _ = make_task([make_run("arrêté", ("terminé",))])

    with pytest.raises(RuntimeError, match=r"^RUN_FAILED: .*arrêté"):
        await run_task(task)


async def test_timeout_stops_and_cleans_up() -> None:
    ticks = iter(range(0, 1000, 60))
    task, _, client = make_task(
        [make_run("en_cours", ("en_cours",))] * 5, clock=lambda: float(next(ticks)), run_timeout=100.0
    )

    with pytest.raises(RuntimeError, match=r"^RUN_TIMEOUT: .*n'est pas terminé"):
        await run_task(task)

    client.runs.stop.assert_called_once()
    client.analyses.delete.assert_called_once()


async def test_unknown_analyse_id_is_the_consumer_s_fault() -> None:
    task, _, client = make_task([])
    client.runs.create.side_effect = NotFoundError("Analyse introuvable", status_code=404)

    with pytest.raises(RuntimeError, match=rf"^ANALYSIS_NOT_FOUND: L'analyse {ANALYSE_ID} est introuvable"):
        await run_task(task, {"analyse_id": ANALYSE_ID, "files": BODY["files"]})

    client.analyses.delete.assert_not_called()  # aucune analyse créée par la tâche
    client.runs.stop.assert_not_called()  # aucun run créé


async def test_not_found_after_creating_the_analysis_is_an_upstream_error() -> None:
    task, _, client = make_task([])
    client.runs.create.side_effect = NotFoundError("Analyse introuvable", status_code=404)

    with pytest.raises(RuntimeError, match=r"^UPSTREAM_ERROR: "):
        await run_task(task)

    client.analyses.delete.assert_called_once_with(uuid.UUID(ANALYSE_ID))


@pytest.mark.parametrize(
    ("erreur", "code"),
    [
        (
            ServerError("Internal Server Error http://millefeuille-backend:8000/api/ephemeral/runs", status_code=500),
            "UPSTREAM_ERROR",
        ),
        (ConnectionFailedError("POST /ephemeral/runs : [Errno 111] Connection refused"), "UPSTREAM_ERROR"),
        (AuthenticationError("Token invalide X-App-Token", status_code=401), "UPSTREAM_ERROR"),
        (MilleFeuilleValidationError("labels: at least one label required", status_code=422), "INVALID_REQUEST"),
    ],
    ids=["5xx", "reseau", "401", "422"],
)
async def test_backend_errors_are_translated_to_neutral_codes(erreur: Exception, code: str) -> None:
    task, _, client = make_task([])
    client.runs.create.side_effect = erreur

    with pytest.raises(RuntimeError, match=rf"^{code}: ") as exc:
        await run_task(task)

    message = str(exc.value)
    assert not any(marque in message for marque in ("http", "8000", "ephemeral", "Errno", "X-App-Token", "labels"))
    client.analyses.delete.assert_called_once_with(uuid.UUID(ANALYSE_ID))


async def test_missing_file_in_storage_is_reported_before_download() -> None:
    task, s3, client = make_task([])
    s3.get_size.side_effect = FileNotFoundError("absent")

    with pytest.raises(RuntimeError, match=r"^FILE_NOT_FOUND: .*cni.pdf"):
        await run_task(task)

    s3.download.assert_not_called()
    client.runs.create.assert_not_called()


async def test_unexpected_exception_is_a_generic_technical_failure() -> None:
    task, s3, _ = make_task([])
    s3.download.side_effect = OSError("disque plein sur /var/lib/worker")

    with pytest.raises(RuntimeError, match=r"^WORKER_ERROR: ") as exc:
        await run_task(task)

    assert "disque" not in str(exc.value)


async def test_cancellation_cleans_up_the_run() -> None:
    polled = threading.Event()

    def get(_: Any) -> EphemeralRun:
        polled.set()
        return make_run("en_cours", ("en_cours",))

    task, _, client = make_task([], poll_interval=30)
    client.runs.get.side_effect = get

    job = asyncio.create_task(task.execute(message(), AsyncMock()))
    assert await asyncio.to_thread(polled.wait, 5)
    await asyncio.sleep(0.05)  # le worker dort entre deux interrogations
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job

    client.runs.stop.assert_called_once()
    client.runs.delete.assert_called_once()


async def test_cleanup_errors_do_not_mask_the_original_failure() -> None:
    task, _, client = make_task([make_run("échec", ("échec",))])
    client.runs.stop.side_effect = NotFoundError("x", status_code=404)
    client.analyses.delete.side_effect = NotFoundError("x", status_code=404)

    with pytest.raises(RuntimeError, match=r"^RUN_FAILED: "):
        await run_task(task)


# --- résultat : dépôt sur le stockage et résumé borné --------------------------------------


def make_big_run(
    pages: int, entites_par_page: int = 2, sortie_agent: str = "sortie", *, valeurs_par_page: bool = False
) -> EphemeralRun:
    """Un run d'un document à `pages` pages, chaque page classée et porteuse d'entités (les mêmes
    valeurs sur chaque page, ou une valeur propre à chaque page avec `valeurs_par_page`)."""
    payload = example("EphemeralRunOut", id=RUN_ID, status="terminé", ttl_hours=48, expires_at=None)
    page = payload["documents"][0]["pages"][0]
    label = {**page["predictions"][0], "kind": "label", "name": "CNI", "value": "CNI", "source": "textual"}

    def entites(n: int) -> list[dict[str, Any]]:
        suffixe = f" p{n}" if valeurs_par_page else ""
        return [
            {
                **page["predictions"][0],
                "kind": "entity",
                "name": f"entite_{i}",
                "value": f"valeur {i}{suffixe}",
                "source": "textual",
            }
            for i in range(entites_par_page)
        ]

    payload["documents"][0]["name"] = "cni.pdf"
    payload["documents"][0]["pages"] = [
        {**page, "page_number": n + 1, "content": "texte " * 500, "predictions": [label, *entites(n)]}
        for n in range(pages)
    ]
    step = payload["execution_steps"][0]
    payload["execution_steps"] = [{**step, "label": "vérification", "status": "terminé", "output": sortie_agent}]
    return EphemeralRun.model_validate(payload)


async def test_result_is_deposited_under_the_client_prefix_with_a_deterministic_key() -> None:
    task, s3, _ = make_task([make_big_run(pages=2)])

    response, _ = await run_task(task)

    cle, charge = s3.upload.call_args.args
    assert cle == "astree/task-1/resultat.json" == response["resultat_file_id"]
    run_complet = json.loads(charge)
    assert run_complet["id"] == RUN_ID
    assert len(run_complet["documents"][0]["pages"]) == 2
    assert "s3_key" not in run_complet["documents"][0]
    assert run_complet["documents"][0]["pages"][0]["content"].startswith("texte")  # le fichier garde tout
    assert response["resultat_octets"] == len(charge)


async def test_summary_carries_labels_per_page_and_entities_per_document() -> None:
    task, _, _ = make_task([make_big_run(pages=3, entites_par_page=1)])

    response, _ = await run_task(task)

    document = response["documents"][0]
    assert document["name"] == "cni.pdf" and document["page_count"] == 3
    assert [page["page_number"] for page in document["pages"]] == [1, 2, 3]
    assert document["pages"][0]["labels"] == [{"name": "CNI", "confidence": 0.5, "source": "textual"}]
    assert document["entities"] == [
        {"name": "entite_0", "value": "valeur 0", "confidence": 0.5, "source": "textual", "pages": [1, 2, 3]}
    ]
    assert "content" not in json.dumps(document)  # le texte des pages ne voyage pas dans le message


async def test_summary_of_a_large_run_stays_under_the_bound_and_says_so() -> None:
    task, _, _ = make_task([make_big_run(pages=400, entites_par_page=20, valeurs_par_page=True)])

    response, _ = await run_task(task)

    assert len(json.dumps(response, ensure_ascii=False).encode("utf-8")) <= 256 * 1024
    assert response["tronque"] is True
    assert response["documents"][0]["page_count"] == 400
    assert 0 < len(response["documents"][0]["entities"]) < 8000  # réduit, pas vidé


async def test_summary_of_a_moderate_run_is_complete() -> None:
    task, _, _ = make_task([make_big_run(pages=40, entites_par_page=5, valeurs_par_page=True)])

    response, _ = await run_task(task)

    assert response["tronque"] is False
    assert len(response["documents"][0]["entities"]) == 200


async def test_long_agent_output_is_truncated_in_the_summary_only() -> None:
    task, s3, _ = make_task([make_big_run(pages=1, sortie_agent="x" * (70 * 1024))])

    response, _ = await run_task(task)

    agent = response["agents"][0]
    assert agent["tronque"] is True and len(agent["output"]) == 64 * 1024
    assert len(json.loads(s3.upload.call_args.args[1])["execution_steps"][0]["output"]) == 70 * 1024


async def test_files_of_two_clients_are_refused_before_any_io() -> None:
    task, s3, client = make_task([])
    body = {**BODY, "files": [{"file_id": "astree/a1/a.pdf"}, {"file_id": "autre/a1/b.pdf"}]}

    with pytest.raises(RuntimeError, match=r"^INVALID_REQUEST: Les fichiers doivent tous appartenir au même client"):
        await run_task(task, body)

    s3.get_size.assert_not_called()
    client.runs.create.assert_not_called()


async def test_deposit_failure_is_a_technical_failure_and_cleans_up() -> None:
    task, s3, client = make_task([make_big_run(pages=1)])
    s3.upload.side_effect = OSError("bucket en lecture seule")

    with pytest.raises(RuntimeError, match=r"^WORKER_ERROR: "):
        await run_task(task)

    client.runs.stop.assert_called_once()
    client.runs.delete.assert_called_once()
