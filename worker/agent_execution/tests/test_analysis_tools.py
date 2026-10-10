"""Tests des outils du chat pour l'analyse de dossier (issue #115)."""

import json

import httpx

from app import chat_graph
from app.analysis_tools import MAX_PROPOSALS_PER_ANSWER, PROMPT_VERSION, AnalysisProposer, proposals_marker
from app.tools import AgentTools

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
    def __init__(self, *, analysis: dict | None = ANALYSIS, refuse_with: tuple[int, str] | None = None) -> None:
        self.analysis = analysis
        self.refuse_with = refuse_with
        self.proposals: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/dossiers/dossier-1/analysis"):
            return httpx.Response(200, json=self.analysis) if self.analysis else httpx.Response(404)
        if path.endswith("/dossiers/dossier-1/analysis/proposals"):
            if self.refuse_with:
                return httpx.Response(self.refuse_with[0], json={"detail": self.refuse_with[1]})
            body = json.loads(request.content)
            self.proposals.append(body)
            return httpx.Response(201, json={"id": f"prop-{len(self.proposals)}", **body})
        return httpx.Response(404)

    def proposer(self, **overrides) -> AnalysisProposer:
        client = httpx.Client(base_url="http://backend/api/internal", transport=httpx.MockTransport(self.handler))
        params = {
            "client": client,
            "dossier_id": "dossier-1",
            "user_id": "user-42",
            "model": "llm-test",
            "source_message_id": "msg-9",
        }
        return AnalysisProposer(**{**params, **overrides})


def _tools(backend: _Backend) -> AgentTools:
    return AgentTools({"id": "dossier-1", "documents": []}, analysis=backend.proposer())


def _names(tools: AgentTools) -> set[str]:
    return {t["function"]["name"] for t in tools.tool_definitions()}


# --- Les outils n'existent que si le dossier a une analyse ---


def test_analysis_tools_are_offered_when_the_dossier_has_an_analysis() -> None:
    names = _names(_tools(_Backend()))
    assert {"view_analysis", "propose_update"} <= names


def test_analysis_tools_are_absent_without_analysis() -> None:
    names = _names(_tools(_Backend(analysis=None)))
    assert "propose_update" not in names and "view_analysis" not in names


def test_agents_without_a_proposer_do_not_get_the_tools() -> None:
    tools = AgentTools({"id": "dossier-1", "documents": []})
    assert not tools.has_analysis
    assert "propose_update" not in _names(tools)
    assert tools.analysis_proposals() is None


# --- view_analysis ---


def test_view_analysis_lists_ids_values_and_review_flags() -> None:
    result = _tools(_Backend()).dispatch_tool("view_analysis", {})
    assert "3 élément(s)" in result
    assert "id=el-nom | entity | nom = Dupond" in result
    assert "id=el-cls | classification | Type de document = CNI [à revoir]" in result


# --- propose_update ---


def test_propose_update_stores_a_pending_proposal_for_the_user() -> None:
    backend = _Backend()
    tools = _tools(backend)

    result = tools.dispatch_tool(
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


def test_proposed_value_shape_follows_the_element_kind() -> None:
    backend = _Backend()
    tools = _tools(backend)
    tools.dispatch_tool("propose_update", {"element_id": "el-cls", "value": "Passeport", "reason": "r"})
    assert backend.proposals[0]["value"] == {"label": "Passeport"}


def test_propose_update_can_add_a_new_element() -> None:
    backend = _Backend()
    tools = _tools(backend)
    tools.dispatch_tool(
        "propose_update",
        {"kind": "entity", "name": "téléphone", "value": "06 12 34 56 78", "reason": "Donné au téléphone"},
    )
    [body] = backend.proposals
    assert body["kind"] == "entity" and body["definition_name"] == "téléphone"
    assert "element_id" not in body


def test_propose_update_rejects_bad_requests_without_calling_the_backend() -> None:
    backend = _Backend()
    tools = _tools(backend)
    unknown = tools.dispatch_tool("propose_update", {"element_id": "nope", "value": "x", "reason": "r"})
    relation = tools.dispatch_tool("propose_update", {"element_id": "el-rel", "value": "x", "reason": "r"})
    no_target = tools.dispatch_tool("propose_update", {"value": "x", "reason": "r"})
    empty = tools.dispatch_tool("propose_update", {"element_id": "el-nom", "value": "  ", "reason": "r"})
    assert "introuvable" in unknown
    assert "relations" in relation
    assert "element_id" in no_target
    assert "obligatoires" in empty
    assert backend.proposals == []
    assert tools.analysis_proposals() is None


def test_propose_update_limits_the_number_of_proposals_per_answer() -> None:
    backend = _Backend()
    tools = _tools(backend)
    for index in range(MAX_PROPOSALS_PER_ANSWER + 2):
        result = tools.dispatch_tool("propose_update", {"element_id": "el-nom", "value": f"v{index}", "reason": "r"})
    assert len(backend.proposals) == MAX_PROPOSALS_PER_ANSWER
    assert "Limite" in result


def test_a_refused_proposal_is_reported_to_the_llm_and_not_recorded() -> None:
    backend = _Backend(refuse_with=(409, "Cette analyse est figée"))
    tools = _tools(backend)
    result = tools.dispatch_tool("propose_update", {"element_id": "el-nom", "value": "x", "reason": "r"})
    assert "refusée" in result and "figée" in result
    assert tools.analysis_proposals() is None


def test_a_broken_backend_does_not_break_the_chat() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(base_url="http://backend/api/internal", transport=httpx.MockTransport(handler))
    tools = AgentTools(
        {"id": "dossier-1", "documents": []},
        analysis=AnalysisProposer(client, "dossier-1", "u", None, None),
    )
    assert not tools.has_analysis
    assert "propose_update" not in _names(tools)


# --- Prompt et marqueur ---


def test_system_prompt_only_mentions_proposals_when_available() -> None:
    with_proposals = chat_graph._build_system_prompt([], [], can_propose_updates=True)
    without = chat_graph._build_system_prompt([], [], can_propose_updates=False)
    assert "propose_update" in with_proposals and "n'applique rien" in with_proposals
    assert "propose_update" not in without


def test_proposals_marker_is_an_invisible_html_comment() -> None:
    marker = proposals_marker("analysis-1", ["p1", "p2"])
    assert marker == "\n\n<!--analysis-proposals:analysis-1:p1,p2-->"


# --- De bout en bout dans le graphe du chat (LLM simulé) ---


class _FakeLLM:
    """LLM qui appelle d'abord propose_update, puis répond."""

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.requests: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        from types import SimpleNamespace as NS

        self.requests.append(kwargs)
        step = self.script.pop(0)
        calls = [
            NS(id=f"call-{i}", function=NS(name=name, arguments=json.dumps(args)))
            for i, (name, args) in enumerate(step.get("calls", []))
        ]
        message = NS(content=step.get("content", ""), tool_calls=calls or None)
        return NS(choices=[NS(message=message)])


def test_chat_proposes_then_appends_the_proposals_marker(monkeypatch) -> None:
    backend = _Backend()
    tools = _tools(backend)
    llm = _FakeLLM(
        [
            {"calls": [("propose_update", {"element_id": "el-nom", "value": "Dupont", "reason": "Vérifié"})]},
            {"content": "Je te propose de corriger le nom en « Dupont »."},
        ]
    )
    monkeypatch.setattr(chat_graph, "_client", lambda: llm)
    events: list[tuple[str, dict]] = []

    answer, _ = chat_graph.run_chat(
        conversation_history=[{"role": "user", "content": "Le nom est Dupont, j'ai vérifié."}],
        tools=tools,
        on_event=lambda kind, data: events.append((kind, data)),
    )

    assert answer.startswith("Je te propose de corriger le nom")
    assert answer.endswith("<!--analysis-proposals:analysis-1:prop-1-->")
    # Les outils et la consigne ont bien été fournis au LLM.
    first = llm.requests[0]
    assert "propose_update" in {t["function"]["name"] for t in first["tools"]}
    assert "propose_update" in first["messages"][0]["content"]
    # L'appel d'outil est visible dans le chat (étape d'outil).
    assert (
        "tool_call",
        {"tool_name": "propose_update", "arguments": {"element_id": "el-nom", "value": "Dupont", "reason": "Vérifié"}},
    ) in events
    # Rien n'est appliqué : seule une proposition en attente a été déposée.
    assert len(backend.proposals) == 1


def test_chat_without_proposal_has_no_marker(monkeypatch) -> None:
    backend = _Backend()
    llm = _FakeLLM([{"content": "Voici l'information demandée."}])
    monkeypatch.setattr(chat_graph, "_client", lambda: llm)
    answer, _ = chat_graph.run_chat(
        conversation_history=[{"role": "user", "content": "Quel est le nom ?"}], tools=_tools(backend)
    )
    assert answer == "Voici l'information demandée."
    assert backend.proposals == []


# --- add_note ---


class _NotesBackend:
    def __init__(self, *, refuse: bool = False) -> None:
        self.notes: list[dict] = []
        self.refuse = refuse

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/dossiers/dossier-1/notes"):
            if self.refuse:
                return httpx.Response(404, json={"detail": "Dossier introuvable"})
            body = json.loads(request.content)
            self.notes.append(body)
            return httpx.Response(201, json={"id": f"note-{len(self.notes)}", **body})
        return httpx.Response(404)

    def tools(self) -> AgentTools:
        from app.note_tools import NoteWriter

        client = httpx.Client(base_url="http://backend/api/internal", transport=httpx.MockTransport(self.handler))
        writer = NoteWriter(client=client, dossier_id="dossier-1", user_id="user-42")
        return AgentTools({"id": "dossier-1", "documents": []}, notes=writer)


def test_add_note_is_exposed_only_when_the_chat_can_write_notes() -> None:
    assert "add_note" in _names(_NotesBackend().tools())
    assert "add_note" not in _names(AgentTools({"id": "dossier-1", "documents": []}))


def test_add_note_stores_an_internal_note_for_the_user() -> None:
    backend = _NotesBackend()
    tools = backend.tools()

    result = tools.dispatch_tool("add_note", {"content": "  Appel de l'avocat du requérant  "})

    assert backend.notes == [{"content": "Appel de l'avocat du requérant", "author": "chat-agent:user-42"}]
    assert "Note enregistrée" in result


def test_add_note_ignores_repeats_and_empty_notes_and_is_bounded() -> None:
    backend = _NotesBackend()
    tools = backend.tools()

    assert "obligatoire" in tools.dispatch_tool("add_note", {"content": "   "})
    tools.dispatch_tool("add_note", {"content": "Pièce vérifiée"})
    assert "déjà été ajoutée" in tools.dispatch_tool("add_note", {"content": " pièce   VÉRIFIÉE "})
    tools.dispatch_tool("add_note", {"content": "Deuxième note"})
    tools.dispatch_tool("add_note", {"content": "Troisième note"})
    assert "Limite atteinte" in tools.dispatch_tool("add_note", {"content": "Quatrième note"})
    assert len(backend.notes) == 3


def test_add_note_reports_a_refused_note_to_the_model() -> None:
    backend = _NotesBackend(refuse=True)
    assert "pas pu être enregistrée" in backend.tools().dispatch_tool("add_note", {"content": "Une note"})
