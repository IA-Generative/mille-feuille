"""Le choix du modèle : le premier fait tout par défaut, le mode auto choisit selon la difficulté."""

import pytest

from app.agent import model_router
from app.agent.model_router import Choice

pytestmark = pytest.mark.anyio

SMALL, MEDIUM, BIG = Choice("petit", 1), Choice("moyen", 2), Choice("grand", 3)


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch):
    """Les modèles de la table (le préféré d'abord), sans base."""

    def install(*choices: Choice, auto: bool = False) -> None:
        async def fake() -> list[Choice]:
            return list(choices)

        monkeypatch.setattr(model_router, "_models", fake)
        monkeypatch.setattr(model_router.settings, "LLM_AUTO_MODE", auto)

    return install


def test_the_lightest_model_that_is_strong_enough_is_picked() -> None:
    models = [BIG, SMALL, MEDIUM]

    assert model_router.pick(models, 1) == "petit"
    assert model_router.pick(models, 2) == "moyen"
    assert model_router.pick(models, 3) == "grand"


def test_when_no_model_is_strong_enough_the_strongest_is_picked() -> None:
    assert model_router.pick([SMALL, MEDIUM], 3) == "moyen"


def test_at_equal_level_the_preferred_model_wins() -> None:
    assert model_router.pick([Choice("a", 2), Choice("b", 2)], 2) == "a"


async def test_without_models_in_the_table_the_configured_model_is_used(models, monkeypatch) -> None:
    models()
    monkeypatch.setattr(model_router.settings, "LLM_MODEL", "configuré")

    assert await model_router.default_model() == "configuré"
    assert await model_router.for_query("Bonjour") == "configuré"


async def test_by_default_the_first_model_does_everything(models) -> None:
    models(BIG, SMALL)

    assert await model_router.for_query("Une question difficile") == "grand"
    assert await model_router.for_difficulty(1) == "grand"
    assert await model_router.light_model() == "grand"


async def test_an_explicit_model_always_wins(models) -> None:
    models(SMALL, BIG, auto=True)

    assert await model_router.for_query("Une question", explicit="imposé") == "imposé"
    assert await model_router.for_difficulty(3, explicit="imposé") == "imposé"


async def test_in_auto_mode_the_difficulty_of_the_query_decides(models, monkeypatch) -> None:
    models(SMALL, BIG, auto=True)
    asked: list[str] = []

    async def classify(query: str, available: list[Choice]) -> int:
        asked.append(query)
        return 3 if "juridique" in query else 1

    monkeypatch.setattr(model_router, "classify", classify)

    assert await model_router.for_query("Quel est son nom ?") == "petit"
    assert await model_router.for_query("Analyse juridique du contrat") == "grand"
    assert len(asked) == 2


async def test_auto_mode_does_not_classify_when_all_models_have_the_same_level(models, monkeypatch) -> None:
    models(Choice("a", 2), Choice("b", 2), auto=True)

    async def classify(query: str, available: list[Choice]) -> int:
        raise AssertionError("pas de classification utile")

    monkeypatch.setattr(model_router, "classify", classify)

    assert await model_router.for_query("Question") == "a"


async def test_in_auto_mode_the_light_model_is_the_lowest_level(models) -> None:
    models(BIG, SMALL, auto=True)

    assert await model_router.light_model() == "petit"
    assert await model_router.for_difficulty(2) == "grand"


async def test_a_failing_classification_falls_back_to_the_default_difficulty(monkeypatch) -> None:
    from app.agent import llm

    async def failing(**kwargs):
        raise RuntimeError("hub indisponible")

    monkeypatch.setattr(llm, "complete", failing)

    assert await model_router.classify("Question", [SMALL, BIG]) == model_router.DEFAULT_DIFFICULTY
