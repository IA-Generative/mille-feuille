"""Outils du chat pour l'analyse du dossier (issue #115) et pour les notes internes : les propositions n'appliquent
rien, les notes s'enregistrent tout de suite. Les outils lisent et écrivent en base ; quelques tests simulent la base
pour les cas limites, les autres passent par la vraie (sur la boucle de l'application, `client.portal`)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.agent.analysis_tools import MAX_PROPOSALS_PER_ANSWER, PROMPT_VERSION, AnalysisProposer, proposals_marker
from app.agent.note_tools import NoteWriter
from app.agent.tools import AgentTools
from app.db import async_session_factory
from app.models.dossier_analysis import (
    AnalysisElementKind,
    DossierAnalysisStatus,
    ElementVersionOrigin,
)
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository

pytestmark = pytest.mark.anyio

ANALYSIS = {
    "id": "analysis-1",
    "elements": [
        {
            "id": "el-nom",
            "kind": "entity",
            "definition_name": "nom",
            "needs_review": False,
            "retained_version": {"value": {"value": "Dupond"}},
        },
        {
            "id": "el-cls",
            "kind": "classification",
            "definition_name": "Type de document",
            "needs_review": True,
            "retained_version": {"value": {"label": "CNI"}},
        },
        {
            "id": "el-rel",
            "kind": "relation",
            "definition_name": "habite à",
            "needs_review": False,
            "retained_version": {"value": {"type": "habite à"}},
        },
    ],
}


class _Backend:
    """L'analyse du dossier et le dépôt des propositions, simulés : ce qui a été déposé est gardé."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, analysis: dict | None = ANALYSIS, refuse: str | None = None):
        self.analysis = analysis
        self.refuse = refuse
        self.proposals: list[dict] = []
        backend = self

        async def load(self: AnalysisProposer) -> None:
            self._analysis = backend.analysis

        async def create(self: AnalysisProposer, body: dict) -> str:
            if backend.refuse:
                raise ValueError(backend.refuse)
            backend.proposals.append(body)
            return f"prop-{len(backend.proposals)}"

        monkeypatch.setattr(AnalysisProposer, "load", load)
        monkeypatch.setattr(AnalysisProposer, "_create", create)

    async def tools(self) -> AgentTools:
        proposer = AnalysisProposer("dossier-1", "user-42", "llm-test", "msg-9")
        await proposer.load()
        return AgentTools({"id": "dossier-1", "documents": []}, analysis=proposer)


def _names(tools: AgentTools) -> set[str]:
    return {t["function"]["name"] for t in tools.tool_definitions()}


# --- Les outils n'existent que si le dossier a une analyse ---


async def test_analysis_tools_are_offered_when_the_dossier_has_an_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    names = _names(await _Backend(monkeypatch).tools())
    assert {"view_analysis", "propose_update"} <= names


async def test_analysis_tools_are_absent_without_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    names = _names(await _Backend(monkeypatch, analysis=None).tools())
    assert "propose_update" not in names and "view_analysis" not in names


def test_agents_without_a_proposer_do_not_get_the_tools() -> None:
    tools = AgentTools({"id": "dossier-1", "documents": []})
    assert not tools.has_analysis
    assert "propose_update" not in _names(tools)
    assert tools.analysis_proposals() is None


# --- view_analysis ---


async def test_view_analysis_lists_ids_values_and_review_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    result = await (await _Backend(monkeypatch).tools()).dispatch_tool("view_analysis", {})
    assert "3 élément(s)" in result
    assert "id=el-nom | entity | nom = Dupond" in result
    assert "id=el-cls | classification | Type de document = CNI [à revoir]" in result


# --- propose_update ---


async def test_propose_update_stores_a_pending_proposal_for_the_user(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _Backend(monkeypatch)
    tools = await backend.tools()

    result = await tools.dispatch_tool(
        "propose_update", {"element_id": "el-nom", "value": "Dupont", "reason": "Vérifié par téléphone"}
    )

    [body] = backend.proposals
    assert body == {
        "proposed_by": "chat-agent:user-42",
        "value": {"value": "Dupont"},
        "reason": "Vérifié par téléphone",
        "source_type": "chat_message",
        "source_id": "msg-9",
        "model": "llm-test",
        "prompt_version": PROMPT_VERSION,
        "element_id": "el-nom",
    }
    # Le LLM est averti que rien n'est appliqué.
    assert "EN ATTENTE" in result
    assert tools.analysis_proposals() == ("analysis-1", ["prop-1"])


async def test_the_same_proposal_is_not_deposited_twice_in_one_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _Backend(monkeypatch)
    tools = await backend.tools()
    args = {"element_id": "el-nom", "value": "Marek ILIEV", "reason": "Le requérant est Marek ILIEV"}

    first = await tools.dispatch_tool("propose_update", args)
    repeats = [await tools.dispatch_tool("propose_update", {**args, "value": " marek iliev "}) for _ in range(4)]

    assert len(backend.proposals) == 1
    assert tools.analysis_proposals() == ("analysis-1", ["prop-1"])
    assert "EN ATTENTE" in first
    assert all("existe déjà" in r for r in repeats)


async def test_a_new_element_and_a_different_value_are_still_proposed(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _Backend(monkeypatch)
    tools = await backend.tools()

    await tools.dispatch_tool(
        "propose_update", {"kind": "entity", "name": "adresse", "value": "1 rue A", "reason": "r"}
    )
    await tools.dispatch_tool(
        "propose_update", {"kind": "entity", "name": "adresse", "value": "2 rue B", "reason": "r"}
    )
    await tools.dispatch_tool("propose_update", {"kind": "entity", "name": "ville", "value": "1 rue A", "reason": "r"})

    assert len(backend.proposals) == 3


async def test_proposed_value_shape_follows_the_element_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _Backend(monkeypatch)
    tools = await backend.tools()
    await tools.dispatch_tool("propose_update", {"element_id": "el-cls", "value": "Passeport", "reason": "r"})
    assert backend.proposals[0]["value"] == {"label": "Passeport"}


async def test_propose_update_can_add_a_new_element(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _Backend(monkeypatch)
    tools = await backend.tools()
    await tools.dispatch_tool(
        "propose_update",
        {"kind": "entity", "name": "téléphone", "value": "06 12 34 56 78", "reason": "Donné au téléphone"},
    )
    [body] = backend.proposals
    assert body["kind"] == "entity" and body["definition_name"] == "téléphone"
    assert "element_id" not in body


async def test_propose_update_rejects_bad_requests_without_depositing(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _Backend(monkeypatch)
    tools = await backend.tools()
    unknown = await tools.dispatch_tool("propose_update", {"element_id": "nope", "value": "x", "reason": "r"})
    relation = await tools.dispatch_tool("propose_update", {"element_id": "el-rel", "value": "x", "reason": "r"})
    no_target = await tools.dispatch_tool("propose_update", {"value": "x", "reason": "r"})
    empty = await tools.dispatch_tool("propose_update", {"element_id": "el-nom", "value": "  ", "reason": "r"})
    assert "introuvable" in unknown
    assert "relations" in relation
    assert "element_id" in no_target
    assert "obligatoires" in empty
    assert backend.proposals == []
    assert tools.analysis_proposals() is None


async def test_propose_update_limits_the_number_of_proposals_per_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _Backend(monkeypatch)
    tools = await backend.tools()
    for index in range(MAX_PROPOSALS_PER_ANSWER + 2):
        result = await tools.dispatch_tool(
            "propose_update", {"element_id": "el-nom", "value": f"v{index}", "reason": "r"}
        )
    assert len(backend.proposals) == MAX_PROPOSALS_PER_ANSWER
    assert "Limite" in result


async def test_a_refused_proposal_is_reported_to_the_llm_and_not_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = await _Backend(monkeypatch, refuse="Cette analyse est figée").tools()
    result = await tools.dispatch_tool("propose_update", {"element_id": "el-nom", "value": "x", "reason": "r"})
    assert "refusée" in result and "figée" in result
    assert tools.analysis_proposals() is None


async def test_a_database_that_does_not_answer_does_not_break_the_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> None:
        raise ConnectionError("base injoignable")

    monkeypatch.setattr("app.agent.analysis_tools.async_session_factory", broken)
    proposer = AnalysisProposer("dossier-1", "u", None, None)
    await proposer.load()
    tools = AgentTools({"id": "dossier-1", "documents": []}, analysis=proposer)
    assert not tools.has_analysis
    assert "propose_update" not in _names(tools)


def test_proposals_marker_is_an_invisible_html_comment() -> None:
    marker = proposals_marker("analysis-1", ["p1", "p2"])
    assert marker == "\n\n<!--analysis-proposals:analysis-1:p1,p2-->"


# --- Avec la vraie base ---


def _dossier_with_analysis(client: TestClient, name: str) -> tuple[str, str]:
    analyse_id = client.post("/api/analyses", json={"name": f"Analyse {name}", "description": "Test"}).json()["id"]
    dossier_id = client.post("/api/dossiers", json={"name": name, "analyse_id": analyse_id}).json()["id"]

    async def setup() -> str:
        async with async_session_factory() as db:
            repository = DossierAnalysisRepository(db)
            analysis = await repository.create_analysis(uuid.UUID(dossier_id))
            element = await repository.create_element(
                analysis,
                kind=AnalysisElementKind.ENTITY,
                value={"value": "Dupond"},
                definition_name="nom",
                origin=ElementVersionOrigin.MODEL,
            )
            return str(element.id)

    return dossier_id, client.portal.call(setup)


def test_a_proposal_reaches_the_database_and_changes_nothing_else(client: TestClient) -> None:
    dossier_id, element_id = _dossier_with_analysis(client, "Dossier propose en base")

    async def scenario() -> tuple[str, list[str]]:
        proposer = AnalysisProposer(dossier_id, "user-42", "llm-test", None)
        await proposer.load()
        assert proposer.available and f"id={element_id} | entity | nom = Dupond" in proposer.list_elements()
        answer = await proposer.propose(value="Dupont", reason="Vérifié par téléphone", element_id=element_id)
        return answer, proposer.proposal_ids

    answer, proposal_ids = client.portal.call(scenario)

    assert "EN ATTENTE" in answer and len(proposal_ids) == 1
    elements = client.get(f"/api/dossiers/{dossier_id}/analyse-dossier").json()["elements"]
    assert elements[0]["retained_version"]["value"] == {"value": "Dupond"}  # rien n'est appliqué


def test_a_frozen_analysis_refuses_proposals(client: TestClient) -> None:
    dossier_id, element_id = _dossier_with_analysis(client, "Dossier figé en base")

    async def scenario() -> str:
        async with async_session_factory() as db:
            analysis = await DossierAnalysisRepository(db).get_current(uuid.UUID(dossier_id))
            analysis.status = DossierAnalysisStatus.FIGEE
            await db.commit()
        proposer = AnalysisProposer(dossier_id, "user-42", None, None)
        await proposer.load()
        return await proposer.propose(value="Dupont", reason="r", element_id=element_id)

    answer = client.portal.call(scenario)

    assert "refusée" in answer and "figée" in answer


def test_add_note_stores_an_internal_note_for_the_user(client: TestClient) -> None:
    dossier_id, _ = _dossier_with_analysis(client, "Dossier note en base")

    async def scenario() -> list[str]:
        writer = NoteWriter(dossier_id, "user-42")
        tools = AgentTools({"id": dossier_id, "documents": []}, notes=writer)
        assert "obligatoire" in await tools.dispatch_tool("add_note", {"content": "   "})
        stored = await tools.dispatch_tool("add_note", {"content": "  Appel de l'avocat du requérant  "})
        repeated = await tools.dispatch_tool("add_note", {"content": " appel de l'avocat   du requérant "})
        assert "Note enregistrée" in stored and "déjà été ajoutée" in repeated
        for text in ("Deuxième note", "Troisième note"):
            await tools.dispatch_tool("add_note", {"content": text})
        assert "Limite atteinte" in await tools.dispatch_tool("add_note", {"content": "Quatrième note"})
        return writer.note_ids

    note_ids = client.portal.call(scenario)

    notes = client.get(f"/api/dossiers/{dossier_id}/notes").json()
    assert len(note_ids) == 3 and {n["id"] for n in notes} == set(note_ids)
    assert any(n["content"] == "Appel de l'avocat du requérant" for n in notes)


def test_add_note_reports_a_missing_dossier_to_the_model(client: TestClient) -> None:
    async def scenario() -> str:
        tools = AgentTools({"id": "x", "documents": []}, notes=NoteWriter(str(uuid.uuid4()), "user-42"))
        return await tools.dispatch_tool("add_note", {"content": "Une note"})

    assert "pas pu être enregistrée" in client.portal.call(scenario)


def test_add_note_is_exposed_only_when_the_chat_can_write_notes() -> None:
    with_notes = AgentTools({"id": "d", "documents": []}, notes=NoteWriter("d", "u"))
    assert "add_note" in _names(with_notes)
    assert "add_note" not in _names(AgentTools({"id": "d", "documents": []}))
