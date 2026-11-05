"""Le choix du modèle : le premier fait tout par défaut, le mode auto suit les capacités que la demande demande."""

import pytest

from app.agent import model_router
from app.agent.model_router import Capability, Catalogue, Choice

pytestmark = pytest.mark.anyio

HEAVY = Capability("heavy", "Tâches lourdes", "Capable de raisonner sur plusieurs documents.")
TOOLS = Capability("tools", "Outils", "Capable de répondre en appelant des outils.")
FIRST = Choice("premier", frozenset())
TOOLED = Choice("outillé", frozenset({"tools"}))
STRONG = Choice("costaud", frozenset({"heavy", "tools"}))


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch):
    """Les modèles et capacités de la table (le préféré d'abord), sans base."""

    def install(*models: Choice, auto: bool = False, capabilities=(HEAVY, TOOLS)) -> None:
        async def fake() -> Catalogue:
            return Catalogue(list(models), list(capabilities), auto)

        monkeypatch.setattr(model_router, "_catalogue", fake)

    return install


def test_the_first_model_that_has_all_the_capabilities_is_picked() -> None:
    models = [FIRST, TOOLED, STRONG]

    assert model_router.pick(models, set()) == "premier"
    assert model_router.pick(models, {"tools"}) == "outillé"
    assert model_router.pick(models, {"heavy", "tools"}) == "costaud"


def test_when_no_model_has_everything_the_one_with_the_most_is_picked() -> None:
    assert model_router.pick([FIRST, TOOLED], {"heavy", "tools"}) == "outillé"
    assert model_router.pick([FIRST, TOOLED], {"heavy"}) == "premier"  # personne : le premier


async def test_without_models_in_the_table_the_configured_model_is_used(catalogue, monkeypatch) -> None:
    catalogue()
    monkeypatch.setattr(model_router.settings, "LLM_MODEL", "configuré")

    assert await model_router.default_model() == "configuré"
    assert await model_router.for_query("Bonjour") == "configuré"


async def test_by_default_the_first_model_does_everything(catalogue) -> None:
    catalogue(STRONG, FIRST)

    assert await model_router.for_query("Une question difficile") == "costaud"
    assert await model_router.planner_model() == "costaud"


async def test_an_explicit_model_always_wins(catalogue) -> None:
    catalogue(FIRST, STRONG, auto=True)

    assert await model_router.for_query("Une question", explicit="imposé") == "imposé"


async def test_in_auto_mode_the_capabilities_of_the_query_decide(catalogue, monkeypatch) -> None:
    catalogue(FIRST, TOOLED, STRONG, auto=True)
    asked: list[str] = []

    async def classify(query: str, available: Catalogue) -> set[str]:
        asked.append(query)
        return {"heavy", "tools"} if "contrat" in query else set()

    monkeypatch.setattr(model_router, "classify", classify)

    assert await model_router.for_query("Quel est son nom ?") == "premier"
    assert await model_router.for_query("Analyse ce contrat") == "costaud"
    assert len(asked) == 2


@pytest.mark.parametrize("models", [(FIRST,), ()])
async def test_auto_mode_does_not_classify_without_a_choice_to_make(catalogue, monkeypatch, models) -> None:
    catalogue(*models, auto=True)

    async def classify(query: str, available: Catalogue) -> set[str]:
        raise AssertionError("pas de classification utile")

    monkeypatch.setattr(model_router, "classify", classify)
    monkeypatch.setattr(model_router.settings, "LLM_MODEL", "configuré")

    assert await model_router.for_query("Question") == (models[0].name if models else "configuré")


async def test_auto_mode_does_not_classify_without_capabilities(catalogue, monkeypatch) -> None:
    catalogue(FIRST, STRONG, auto=True, capabilities=())

    async def classify(query: str, available: Catalogue) -> set[str]:
        raise AssertionError("rien à choisir")

    monkeypatch.setattr(model_router, "classify", classify)

    assert await model_router.for_query("Question") == "premier"


async def test_the_capabilities_named_by_the_model_are_matched_to_the_catalogue(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.agent import llm

    seen: dict = {}

    async def fake(**kwargs):
        seen.update(kwargs)
        content = '{"capabilities": ["outils", "Inconnue", 3]}'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    monkeypatch.setattr(llm, "complete", fake)
    available = Catalogue([FIRST, STRONG], [HEAVY, TOOLS], True)

    assert await model_router.classify("Question", available) == {"tools"}
    assert "Tâches lourdes : Capable de raisonner" in seen["messages"][0]["content"]
    assert seen["model"] == "premier"


async def test_a_failing_classification_leaves_the_first_model(monkeypatch) -> None:
    from app.agent import llm

    async def failing(**kwargs):
        raise RuntimeError("hub indisponible")

    monkeypatch.setattr(llm, "complete", failing)

    assert await model_router.classify("Question", Catalogue([FIRST], [HEAVY], True)) == set()


async def test_the_registered_default_is_none_without_models_and_the_first_otherwise(catalogue) -> None:
    catalogue()
    assert await model_router.registered_default() is None

    catalogue(STRONG, FIRST)
    assert await model_router.registered_default() == "costaud"
