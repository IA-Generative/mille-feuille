import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import async_session_factory
from app.main import app
from app.models.token_usage import TokenUsage
from app.routers.tools import get_tool_chooser
from app.services.tools.mcp_caller import CallTimeoutError
from app.services.tools.model_chooser import ChosenCall, ModelUnavailableError, OpenAiToolChooser, ToolSpec
from tests.access_support import As
from tests.tool_support import FakeCaller, FakeLister, create_server, tool_id


class FakeChooser:
    """Remplace le modèle : il « choisit » toujours les mêmes arguments."""

    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str, ToolSpec]] = []
        self.result: ChosenCall | Exception = ChosenCall(
            model="modele-test", arguments={"mots_cles": "subvention"}, input_tokens=42, output_tokens=7
        )

    async def choose(self, model: str | None, prompt: str, tool: ToolSpec) -> ChosenCall:
        self.calls.append((model, prompt, tool))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def chooser() -> FakeChooser:
    fake = FakeChooser()
    app.dependency_overrides[get_tool_chooser] = lambda: fake
    yield fake
    del app.dependency_overrides[get_tool_chooser]


@pytest.fixture
def server(client: TestClient, lister: FakeLister) -> dict:
    return create_server(client, visibility="all", tools=["rechercher_texte", "envoyer_courriel"])


def run_test(client: TestClient, tool: str, **body):
    return client.post(f"/api/tools/{tool}/test", json={"prompt": "Cherche les subventions", **body})


def usage_of(client: TestClient, user_id: str) -> list[TokenUsage]:
    async def read() -> list[TokenUsage]:
        async with async_session_factory() as session:
            return list((await session.execute(select(TokenUsage).where(TokenUsage.user_id == user_id))).scalars())

    return client.portal.call(read)


def test_the_model_chooses_the_arguments_and_only_the_raw_output_comes_back(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, server: dict
) -> None:
    body = run_test(client, tool_id(server, "rechercher_texte")).json()

    assert (body["ok"], body["output"], body["untrusted"]) == (True, "Article L1111-1 : …", True)
    assert body["call"] == {"name": "rechercher_texte", "arguments": {"mots_cles": "subvention"}}
    assert body["model"] == "modele-test"
    assert caller.calls[0][2:] == ("rechercher_texte", {"mots_cles": "subvention"})


def test_the_model_only_gets_this_tool_and_the_request(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, server: dict
) -> None:
    run_test(client, tool_id(server, "rechercher_texte"))

    _, prompt, spec = chooser.calls[0]
    assert (prompt, spec.name) == ("Cherche les subventions", "rechercher_texte")


def test_the_person_can_choose_the_model(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, server: dict
) -> None:
    run_test(client, tool_id(server, "rechercher_texte"), model="mistral-large")

    assert chooser.calls[0][0] == "mistral-large"


def test_without_a_choice_the_model_is_left_to_the_hub_default(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, server: dict
) -> None:
    run_test(client, tool_id(server, "rechercher_texte"))

    assert chooser.calls[0][0] is None


def test_the_tokens_are_counted_for_the_person(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, server: dict
) -> None:
    run_test(client, tool_id(server, "rechercher_texte"))

    mine = [u for u in usage_of(client, "dev-user") if u.step == "test_tool"]
    assert mine and (mine[-1].model, mine[-1].input_tokens, mine[-1].output_tokens) == ("modele-test", 42, 7)


def test_a_tool_that_modifies_data_needs_an_explicit_confirmation(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, server: dict
) -> None:
    mail = tool_id(server, "envoyer_courriel")

    refused = run_test(client, mail).json()
    assert (refused["ok"], refused["code"]) == (False, "confirmation_requise")
    assert chooser.calls == [] and caller.calls == []  # ni modèle consulté, ni outil appelé

    confirmed = run_test(client, mail, confirmed=True).json()
    assert confirmed["ok"] is True and len(caller.calls) == 1


def test_a_model_that_does_not_call_the_tool_is_reported_with_its_answer(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, server: dict
) -> None:
    chooser.result = ChosenCall(model="modele-test", arguments=None, answer="Je ne vois pas de quoi il s'agit.")

    body = run_test(client, tool_id(server, "rechercher_texte")).json()

    assert (body["ok"], body["code"], body["output"]) == (False, "aucun_appel", "Je ne vois pas de quoi il s'agit.")
    assert body["call"] is None and caller.calls == []


def test_an_unavailable_model_gives_a_clear_code(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, server: dict
) -> None:
    chooser.result = ModelUnavailableError("Le modèle n'a pas répondu.")

    body = run_test(client, tool_id(server, "rechercher_texte")).json()

    assert (body["ok"], body["code"]) == (False, "modele_indisponible")


def test_a_failing_server_is_reported_like_for_an_agent(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, server: dict
) -> None:
    caller.result = CallTimeoutError()

    body = run_test(client, tool_id(server, "rechercher_texte")).json()

    assert (body["ok"], body["code"]) == (False, "delai_depasse")
    assert body["call"]["name"] == "rechercher_texte"  # le modèle a bien choisi, c'est le serveur qui n'a pas répondu


def test_internal_unknown_and_invisible_tools_are_not_tested(
    client: TestClient, chooser: FakeChooser, caller: FakeCaller, lister: FakeLister, world: dict
) -> None:
    with As(world["alice"]):
        private = create_server(client, visibility="private")

    with As(world["bob"]):
        codes = [
            run_test(client, tool).json()["code"]
            for tool in ("calculatrice", "fantome", tool_id(private, "rechercher_texte"))
        ]

    assert codes == ["outil_interne", "outil_inconnu", "outil_inconnu"]
    assert chooser.calls == []


def test_an_empty_request_is_refused(client: TestClient, chooser: FakeChooser, server: dict) -> None:
    response = client.post(f"/api/tools/{tool_id(server, 'rechercher_texte')}/test", json={"prompt": ""})
    assert response.status_code == 422


# --- Le client du hub, simulé au niveau du SDK ---


class FakeCompletions:
    def __init__(self, message: SimpleNamespace | Exception) -> None:
        self.message = message
        self.kwargs: dict = {}

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.message, Exception):
            raise self.message
        return SimpleNamespace(
            choices=[SimpleNamespace(message=self.message)],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=3),
        )


def hub(message: SimpleNamespace | Exception) -> tuple[OpenAiToolChooser, FakeCompletions]:
    completions = FakeCompletions(message)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def default_model() -> str:
        return "defaut-du-hub"

    return OpenAiToolChooser(client, default_model), completions


def tool_call(arguments: str) -> SimpleNamespace:
    return SimpleNamespace(content=None, tool_calls=[SimpleNamespace(function=SimpleNamespace(arguments=arguments))])


SPEC = ToolSpec("rechercher_texte", "Cherche.", {"type": "object", "properties": {"mots_cles": {"type": "string"}}})


def test_the_hub_gets_a_single_tool_and_is_forced_to_call_it() -> None:
    chooser, completions = hub(tool_call(json.dumps({"mots_cles": "loi"})))

    chosen = asyncio.run(chooser.choose("mistral", "Cherche la loi", SPEC))

    assert (chosen.model, chosen.arguments, chosen.input_tokens, chosen.output_tokens) == (
        "mistral",
        {"mots_cles": "loi"},
        11,
        3,
    )
    assert completions.kwargs["tool_choice"] == "required"
    assert [t["function"]["name"] for t in completions.kwargs["tools"]] == ["rechercher_texte"]
    assert completions.kwargs["tools"][0]["function"]["parameters"] == SPEC.input_schema


def test_the_default_model_comes_from_the_hub() -> None:
    chooser, _ = hub(tool_call("{}"))
    assert asyncio.run(chooser.choose(None, "x", SPEC)).model == "defaut-du-hub"


@pytest.mark.parametrize("raw", ["pas du json", "[1, 2]"])
def test_unreadable_arguments_count_as_no_call(raw: str) -> None:
    chooser, _ = hub(tool_call(raw))
    assert asyncio.run(chooser.choose("m", "x", SPEC)).arguments is None


def test_a_text_answer_without_a_call_is_kept() -> None:
    chooser, _ = hub(SimpleNamespace(content="Je ne sais pas.", tool_calls=None))
    chosen = asyncio.run(chooser.choose("m", "x", SPEC))
    assert (chosen.arguments, chosen.answer) == (None, "Je ne sais pas.")


def test_a_failing_hub_or_no_hub_is_a_clear_error() -> None:
    broken, _ = hub(RuntimeError("connection reset by peer: secret-detail"))
    with pytest.raises(ModelUnavailableError) as error:
        asyncio.run(broken.choose("m", "x", SPEC))
    assert "secret-detail" not in str(error.value)

    async def none() -> None:
        return None

    with pytest.raises(ModelUnavailableError):
        asyncio.run(OpenAiToolChooser(None, none).choose("m", "x", SPEC))
    with pytest.raises(ModelUnavailableError):  # aucun modèle de chat sur le hub
        asyncio.run(OpenAiToolChooser(hub(tool_call("{}"))[0]._client, none).choose(None, "x", SPEC))
