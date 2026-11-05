"""Les réponses inexploitables du modèle : un appel d'outil écrit en texte, du JSON à la place d'une réponse, un
message vide. La personne ne doit voir ni du JSON, ni des sources sans réponse."""

import json
from types import SimpleNamespace

import pytest

from app.agent import agent_loop, model_output
from app.agent.chat import answer as answer_module
from app.agent.chat import react
from app.agent.tools import AgentTools
from app.agent.wrap_up import WRAP_UP_NOTICE
from tests.test_agent_chat_tools import NoEvents, ScriptedLlm

pytestmark = pytest.mark.anyio

TOOLS = {"view_entities", "view_classifications"}


def new_tools() -> AgentTools:
    return AgentTools({"documents": [], "execution_steps": []})


async def run_chat(tools: AgentTools | None = None) -> react.LoopResult:
    return await react.run_tool_loop(
        model=None,
        system_prompt="s",
        messages=[{"role": "user", "content": "Quelles entités ?"}],
        tools=tools or new_tools(),
        events=NoEvents(),
    )


@pytest.mark.parametrize(
    "content",
    [
        '{"name": "view_entities", "arguments": {}}',
        '```json\n{"name": "view_entities", "arguments": {}}\n```',
        '{"name": "view_entities", "parameters": {}}',
        '{"function": {"name": "view_entities", "arguments": "{}"}}',
    ],
)
def test_a_tool_call_written_as_text_is_recovered(content: str) -> None:
    call = model_output.recovered_call(content, TOOLS)

    assert call is not None
    assert call["function"]["name"] == "view_entities" and json.loads(call["function"]["arguments"]) == {}


@pytest.mark.parametrize(
    "content",
    [
        "",
        "Voici les entités.",
        '{"query": "OQTF"}',
        '{"name": "inconnu", "arguments": {}}',
        '{"name": "view_entities"',
        "[1]",
    ],
)
def test_other_texts_are_not_tool_calls(content: str) -> None:
    assert model_output.recovered_call(content, TOOLS) is None


def test_only_empty_or_json_texts_are_unusable() -> None:
    assert model_output.unusable("") and model_output.unusable("  \n")
    assert model_output.unusable('{"query": "x"}') and model_output.unusable("```json\n[1]\n```")
    assert not model_output.unusable("Le requérant est né le 3 mars.")
    assert not model_output.unusable("{Le requérant} est né le 3 mars.")


async def test_the_chat_runs_a_tool_call_the_model_wrote_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = ScriptedLlm(monkeypatch, [([], '{"name": "view_entities", "arguments": {}}'), ([], "Aucune entité.")])
    events = NoEvents()

    result = await react.run_tool_loop(
        model=None, system_prompt="s", messages=[{"role": "user", "content": "x"}], tools=new_tools(), events=events
    )

    assert result.answer == "Aucune entité." and len(llm.requests) == 2
    assert [kind for kind, _ in events.sent] == ["tool_call", "tool_result"]
    # Le modèle reçoit le résultat de l'outil comme pour un appel normal.
    assert llm.requests[1]["messages"][-1]["role"] == "tool"


async def test_the_chat_asks_again_once_when_the_answer_is_json_without_a_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = ScriptedLlm(monkeypatch, [([], '{"sujet": "entités"}'), ([], "Voici les entités.")])

    result = await run_chat()

    assert result.answer == "Voici les entités." and len(llm.requests) == 2
    assert llm.requests[1]["messages"][-1] == {"role": "user", "content": model_output.RETRY_NOTICE}


async def test_the_chat_asks_again_once_when_the_answer_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = ScriptedLlm(monkeypatch, [([], ""), ([], "Voici les entités.")])

    result = await run_chat()

    assert result.answer == "Voici les entités." and len(llm.requests) == 2
    # Pas de message d'assistant vide dans l'historique : certains serveurs le refusent.
    assert [m["role"] for m in llm.requests[1]["messages"]] == ["system", "user", "user"]


async def test_the_chat_never_shows_json_or_nothing_after_the_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    ScriptedLlm(monkeypatch, [([], '{"sujet": "a"}'), ([], '{"sujet": "b"}')])
    assert (await run_chat()).answer == model_output.FALLBACK_ANSWER

    ScriptedLlm(monkeypatch, [([], ""), ([], "")])
    assert (await run_chat()).answer == model_output.FALLBACK_ANSWER


async def test_a_normal_answer_is_left_alone_and_costs_one_call(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = ScriptedLlm(monkeypatch, [([], "Le requérant est né le 3 mars.")])

    result = await run_chat()

    assert result.answer == "Le requérant est né le 3 mars." and len(llm.requests) == 1


async def test_the_agent_loop_recovers_and_retries_like_the_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = ScriptedLlm(
        monkeypatch,
        [([], '{"name": "view_entities", "arguments": {}}'), ([], ""), ([], "Synthèse de l'agent.")],
    )

    answer = await agent_loop.run_agent(prompt="p", tools=new_tools())

    assert answer == "Synthèse de l'agent." and len(llm.requests) == 3


async def test_the_agent_loop_gives_the_usual_sentence_when_nothing_usable_comes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ScriptedLlm(monkeypatch, [([], '{"x": 1}'), ([], '{"x": 2}')])

    assert await agent_loop.run_agent(prompt="p", tools=new_tools()) == agent_loop.NO_ANSWER


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("Bonjour, voici", "Bonjour, voici"),
        ("Voir [1] et ```code```", "Voir [1] et ```code```"),
        ('{"answer": "Le requérant a', "Le requérant a"),
        ('{"answer": "Il a dit \\"oui\\" et \\u00e9crit', 'Il a dit "oui" et écrit'),
        ('```json\n{"answer": "Oui', "Oui"),
        ('{"answer": "Coupé en deux \\', "Coupé en deux "),
        ('{"query": "entités"}', ""),
        ('{"query": "entit', ""),
        ("", ""),
    ],
)
def test_only_the_text_of_the_answer_is_shown_while_it_is_written(raw: str, shown: str) -> None:
    assert model_output.visible_answer(raw) == shown


def test_the_shown_text_only_grows_as_the_model_writes() -> None:
    raw = '{"answer": "Le requérant, né à \\"Lyon\\" le 3 mars, est \\u00e9tranger.", "sources": []}'
    previous = ""
    for end in range(len(raw) + 1):
        now = model_output.visible_answer(raw[:end])
        assert now.startswith(previous)
        previous = now
    assert previous == 'Le requérant, né à "Lyon" le 3 mars, est étranger.'


@pytest.mark.parametrize(
    ("raw", "answer"),
    [
        ("Le requérant est né le 3 mars.", "Le requérant est né le 3 mars."),
        ('{"answer": "Oui [1]", "sources": []}', "Oui [1]"),
        ('```json\n{"answer": "Oui"}\n```', "Oui"),
        ('{"answer": "Réponse coupée par la limite', "Réponse coupée par la limite"),
        ("{Le requérant} est né le 3 mars.", "{Le requérant} est né le 3 mars."),
        ('{"query": "entités"}', ""),
        ('{"query": "entit', ""),
        ("", ""),
    ],
)
def test_the_final_answer_is_the_text_or_nothing(raw: str, answer: str) -> None:
    assert model_output.final_answer(raw) == answer


class Chunks:
    """Le flux du modèle : un morceau de texte à la fois, comme `chat.completions.create(stream=True)`."""

    def __init__(self, pieces: list[str]) -> None:
        self.pieces = pieces

    def __aiter__(self):  # noqa: ANN204
        async def generate():  # noqa: ANN202
            for piece in self.pieces:
                delta = SimpleNamespace(content=piece)
                yield SimpleNamespace(model="m", usage=None, choices=[SimpleNamespace(delta=delta)])

        return generate()


class Deltas(NoEvents):
    def __init__(self) -> None:
        super().__init__()
        self.text = ""

    async def delta(self, text: str) -> None:
        self.text += text

    async def flush(self) -> None:
        return None


async def stream(monkeypatch: pytest.MonkeyPatch, pieces: list[str]) -> tuple[str, str]:
    """(ce que le navigateur a reçu, la réponse déposée) pour un modèle qui écrit ces morceaux."""

    async def create(**kwargs: object) -> Chunks:
        return Chunks(pieces)

    async def record(*args: object) -> None:
        return None

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(answer_module.llm, "client", lambda: client)
    monkeypatch.setattr(answer_module.usage, "record", record)
    events = Deltas()
    deposited = await answer_module.stream_answer(model=None, system="s", messages=[], events=events)
    return events.text, deposited


async def test_a_plain_answer_is_streamed_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    sent, deposited = await stream(monkeypatch, ["Le requérant ", "est né ", "le 3 mars."])

    assert sent == deposited == "Le requérant est né le 3 mars."


async def test_json_is_never_sent_to_the_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    sent, deposited = await stream(monkeypatch, ['{"que', 'ry": "entités", ', '"limit": 3}'])

    assert sent == "" and deposited == ""  # rien à montrer : le chat se replie sur les outils


async def test_the_answer_field_of_a_json_is_sent_without_the_json(monkeypatch: pytest.MonkeyPatch) -> None:
    sent, deposited = await stream(monkeypatch, ['{"answer": "Le requé', "rant est né", ' le 3 mars.", "sources": []}'])

    assert sent == deposited == "Le requérant est né le 3 mars."


async def test_a_text_starting_with_a_brace_is_sent_in_the_end(monkeypatch: pytest.MonkeyPatch) -> None:
    sent, deposited = await stream(monkeypatch, ["{Le requérant} ", "est né."])

    assert sent == deposited == "{Le requérant} est né."


def search_turns(*, final: str) -> list[tuple[list[tuple[str, dict]], str]]:
    """Le modèle appelle des outils sans s'arrêter (« Je cherche. »), puis écrit sa réponse quand on la lui demande."""
    return [([("view_entities", {})], "Je cherche."), ([("view_entities", {})], "Encore un instant."), ([], final)]


async def test_the_chat_asks_for_a_written_answer_when_the_tool_limit_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(react.settings, "AGENT_MAX_ITERATIONS", 2)
    llm = ScriptedLlm(monkeypatch, search_turns(final="Voici la réponse, d'après les pages lues."))

    result = await run_chat()

    # Avant : la personne lisait « Encore un instant. » et les sources des pages lues, sans réponse.
    assert result.answer == "Voici la réponse, d'après les pages lues." and len(llm.requests) == 3
    last = llm.requests[2]
    assert last["tool_choice"] == "none" and last["messages"][-1] == {"role": "user", "content": WRAP_UP_NOTICE}
    # Le dernier appel d'outil, jamais exécuté, n'est pas dans l'historique : il reste cohérent.
    assert last["messages"][-2]["role"] == "tool"


async def test_the_chat_keeps_the_last_sentence_when_the_final_answer_comes_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(react.settings, "AGENT_MAX_ITERATIONS", 2)
    ScriptedLlm(monkeypatch, search_turns(final=""))

    assert (await run_chat()).answer == "Encore un instant."


async def test_the_agent_loop_asks_for_a_written_answer_when_the_tool_limit_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(react.settings, "AGENT_MAX_ITERATIONS", 2)
    llm = ScriptedLlm(monkeypatch, search_turns(final="Synthèse après lecture du dossier."))

    answer = await agent_loop.run_agent(prompt="p", tools=new_tools())

    assert answer == "Synthèse après lecture du dossier." and len(llm.requests) == 3
    last = llm.requests[2]
    assert last["tool_choice"] == "none" and last["messages"][-1] == {"role": "user", "content": WRAP_UP_NOTICE}
    assert last["messages"][-2]["role"] == "tool"


async def test_the_agent_loop_gives_the_usual_sentence_when_the_final_answer_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(react.settings, "AGENT_MAX_ITERATIONS", 2)
    ScriptedLlm(monkeypatch, search_turns(final=""))

    assert await agent_loop.run_agent(prompt="p", tools=new_tools()) == agent_loop.NO_ANSWER


SEARCH = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
}
OTHER = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "top": {"type": "integer"}}},
    },
}


def test_arguments_alone_are_recovered_when_one_tool_takes_them() -> None:
    call = model_output.recovered_call('{"query": "OQTF"}', {"search_documents"}, [SEARCH])

    assert call is not None and call["function"]["name"] == "search_documents"
    assert json.loads(call["function"]["arguments"]) == {"query": "OQTF"}


def test_arguments_alone_are_not_guessed_when_several_tools_take_them() -> None:
    assert model_output.recovered_call('{"query": "x"}', {"a", "b"}, [SEARCH, {**OTHER}]) is None


def test_the_conversation_stays_with_the_agent_that_answered_last() -> None:
    from app.agent.analysis_agents import AnalysisAgent
    from app.agent.chat import agent_reply
    from app.agent.chat.prompts import agent_marker

    agents = [AnalysisAgent("1", "Pré-analyse", "p", [], None), AnalysisAgent("2", "Autre", "p", [], None)]
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "Réponse." + agent_marker("Pré-analyse")},
        {"role": "user", "content": "et ensuite ?"},
    ]

    assert agent_reply.previous_agent(messages, agents) is agents[0]
    assert agent_reply.previous_agent([{"role": "assistant", "content": "Réponse."}], agents) is None
