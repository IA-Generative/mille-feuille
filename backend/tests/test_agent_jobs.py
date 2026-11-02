"""Travaux de l'agent menés dans le backend (résumés, suggestion d'analyse) : le LLM est simulé, la base est réelle.

Les travaux tournent sur la boucle de l'application (`client.portal`), celle qui possède le moteur de base."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent.jobs import suggestion as suggestion_job
from app.agent.jobs import summary as summary_job
from app.agent.jobs.suggestion import suggest_dossier_analyse
from app.agent.jobs.summary import run_document_summary, run_dossier_summary
from app.agent.llm import AnalyseSuggestion, SuggestionResult

_INTERNAL_HEADERS = {"X-App-Token": "dev-only-worker-token-not-for-prod"}


def _dossier_with_page(client: TestClient, name: str, content: str | None = "Contrat de bail signé le 3 mai.") -> tuple:
    analyse = client.post("/api/analyses", json={"name": f"Analyse {name}", "description": "Location"}).json()
    dossier = client.post("/api/dossiers", json={"name": name, "analyse_id": analyse["id"]}).json()
    dossier = client.post(
        f"/api/dossiers/{dossier['id']}/documents",
        files=[("files", ("bail.pdf", b"fake-bytes", "application/pdf"))],
    ).json()
    document_id = dossier["documents"][0]["id"]
    if content is not None:
        page = client.post(
            f"/api/internal/documents/{document_id}/pages",
            json={"page_number": 1, "content": content},
            headers=_INTERNAL_HEADERS,
        )
        assert page.status_code == 201
    return analyse["id"], dossier["id"], document_id


def _document(client: TestClient, dossier_id: str) -> dict:
    return client.get(f"/api/dossiers/{dossier_id}").json()["documents"][0]


def test_document_summary_is_deposited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _, dossier_id, document_id = _dossier_with_page(client, "Résumé document")
    seen: list[str] = []

    async def fake_summarize(content: str, **_: object) -> str:
        seen.append(content)
        return "Un bail signé en mai."

    monkeypatch.setattr(summary_job, "summarize_text", fake_summarize)
    client.portal.call(run_document_summary, dossier_id, document_id)

    document = _document(client, dossier_id)
    assert document["summary_status"] == "terminé"
    assert document["summary"]["content"] == "Un bail signé en mai."
    assert "--- Page 1 ---\nContrat de bail signé le 3 mai." in seen[0]


def test_document_without_pages_gets_a_placeholder_without_calling_the_llm(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dossier_id, document_id = _dossier_with_page(client, "Résumé vide", content=None)

    async def must_not_be_called(content: str, **_: object) -> str:
        raise AssertionError("le LLM ne doit pas être appelé")

    monkeypatch.setattr(summary_job, "summarize_text", must_not_be_called)
    client.portal.call(run_document_summary, dossier_id, document_id)

    assert _document(client, dossier_id)["summary"]["content"] == "(document sans contenu textuel)"


def test_a_failing_llm_leaves_the_summary_in_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _, dossier_id, document_id = _dossier_with_page(client, "Résumé en échec")

    async def failing(content: str, **_: object) -> str:
        raise RuntimeError("hub LLM indisponible")

    monkeypatch.setattr(summary_job, "summarize_text", failing)
    client.portal.call(run_document_summary, dossier_id, document_id)

    document = _document(client, dossier_id)
    assert document["summary_status"] == "échec"
    assert document["summary_error"] == "hub LLM indisponible"
    assert document["summary"] is None


def test_dossier_summary_uses_the_documents(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _, dossier_id, _ = _dossier_with_page(client, "Résumé dossier")
    seen: list[str] = []

    async def fake_summarize(content: str, **_: object) -> str:
        seen.append(content)
        return "Dossier de location."

    monkeypatch.setattr(summary_job, "summarize_text", fake_summarize)
    client.portal.call(run_dossier_summary, dossier_id)

    dossier = client.get(f"/api/dossiers/{dossier_id}").json()
    assert dossier["summary_status"] == "terminé"
    assert dossier["summary"]["content"] == "Dossier de location."
    assert "### Document : bail.pdf\nPage 1: Contrat de bail signé le 3 mai." in seen[0]


def test_suggestions_name_the_analyses_and_drop_unknown_ones(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    analyse_id, dossier_id, _ = _dossier_with_page(client, "Suggestion")

    async def fake_suggest(*, dossier_summary: str, analyses: list[dict]) -> SuggestionResult:
        assert any(a["id"] == analyse_id for a in analyses)
        return SuggestionResult(
            suggestions=[
                AnalyseSuggestion(analyse_id=analyse_id, score=0.9, rationale="Un bail."),
                AnalyseSuggestion(analyse_id="00000000-0000-0000-0000-000000000000", score=0.5, rationale="?"),
            ]
        )

    monkeypatch.setattr(suggestion_job, "suggest_analyses", fake_suggest)
    client.portal.call(suggest_dossier_analyse, dossier_id)

    dossier = client.get(f"/api/dossiers/{dossier_id}").json()
    assert dossier["suggestion_status"] == "terminé"
    assert dossier["suggested_analyses"] == [
        {"analyse_id": analyse_id, "name": "Analyse Suggestion", "score": 0.9, "rationale": "Un bail."}
    ]


def test_usage_is_recorded_against_the_dossier(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agent import llm, usage

    _, dossier_id, _ = _dossier_with_page(client, "Consommation")

    class FakeCompletions:
        async def create(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(
                model="modèle-test",
                usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5),
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setattr(llm, "client", lambda: fake_client)
    recorded: list[tuple] = []

    async def spy(model, usage_block, kind=None):  # noqa: ANN001, ANN202
        recorded.append((model, usage_block.prompt_tokens, usage_block.completion_tokens))

    monkeypatch.setattr(usage, "record", spy)

    async def scenario() -> str:
        usage.bind("test", dossier_id=dossier_id)
        return await llm.summarize_text("texte")

    assert client.portal.call(scenario) == "ok"
    assert recorded == [("modèle-test", 12, 5)]


# --- Après l'extraction du texte, le backend lance le résumé et l'indexation ---


def test_the_end_of_the_text_extraction_starts_the_summary_and_the_indexation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dossier_id, document_id = _dossier_with_page(client, "Extraction terminée")
    started: list[tuple[str, tuple]] = []
    monkeypatch.setattr("app.routers.internal.dispatch_document_summary", lambda *a: started.append(("summary", a)))
    monkeypatch.setattr("app.routers.internal.dispatch_index_document", lambda *a: started.append(("index", a)))
    url = f"/api/internal/documents/{document_id}/extraction-status"

    client.put(url, json={"status": "en_cours"}, headers=_INTERNAL_HEADERS)
    assert started == []  # ni pendant l'extraction…
    client.put(url, json={"status": "échec", "error": "illisible"}, headers=_INTERNAL_HEADERS)
    assert started == []  # …ni quand elle échoue
    client.put(url, json={"status": "terminé"}, headers=_INTERNAL_HEADERS)

    assert started == [("summary", (dossier_id, document_id)), ("index", (dossier_id, document_id))]


# --- Au démarrage, ce qu'un pod précédent a laissé « en cours » est déclaré en échec ---


def _mark_summary_running(client: TestClient, dossier_id: str, document_id: str) -> None:
    from app.db import async_session_factory
    from app.models.summary import SummaryStatus
    from app.repositories.dossier_repository import DossierRepository

    async def mark() -> None:
        async with async_session_factory() as db:
            repository = DossierRepository(db)
            document = await repository.get_document_by_id(uuid.UUID(document_id))
            await repository.set_document_summary_status(document, SummaryStatus.EN_COURS)

    client.portal.call(mark)


def test_an_interrupted_summary_is_failed_at_start_up(client: TestClient) -> None:
    from app.agent import dispatch

    _, dossier_id, document_id = _dossier_with_page(client, "Résumé interrompu")
    _mark_summary_running(client, dossier_id, document_id)

    # Seul le travail de ce document est tenu pour mort : la base est partagée avec les autres tests.
    async def only_this_one_is_dead(name: str) -> bool:
        return name != f"document-summary-{document_id}"

    client.portal.call(dispatch._fail_stale_summaries, only_this_one_is_dead)

    document = _document(client, dossier_id)
    assert document["summary_status"] == "échec" and "interrompu" in document["summary_error"]


def test_a_summary_running_on_another_pod_is_left_alone(client: TestClient) -> None:
    from app.agent import dispatch
    from app.agent.runner import agent_runner
    from app.connectors import redis_connector

    _, dossier_id, document_id = _dossier_with_page(client, "Résumé ailleurs")
    _mark_summary_running(client, dossier_id, document_id)
    key = f"agent:job:document-summary-{document_id}"
    redis_connector.client.set(key, 1, ex=30)  # le battement d'un autre pod
    try:
        # Les autres travaux de la base partagée sont tenus pour vivants : seul celui-ci est jugé, par son battement.
        async def judge(name: str) -> bool:
            return name != f"document-summary-{document_id}" or await agent_runner.is_alive(name)

        client.portal.call(dispatch._fail_stale_summaries, judge)
    finally:
        redis_connector.client.delete(key)

    assert _document(client, dossier_id)["summary_status"] == "en_cours"
