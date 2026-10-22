from app.models.analyse import AgentTool
from app.services.tools.internal_catalog import (
    INTERNAL_TOOLS,
    available_internal_tools,
    get_internal_tool,
    is_available,
)

# Retirés du catalogue, avec la raison : un agent qui les garde les voit signalés comme indisponibles.
REMOVED_LEGACY_IDS = {
    "recherche_web": "ce sera un serveur MCP",
    "lecture_document": "outil de lecture du dossier : toujours donné à un agent, il ne se choisit pas",
}


def test_ids_are_unique() -> None:
    ids = [tool.id for tool in INTERNAL_TOOLS]
    assert len(ids) == len(set(ids))


def test_every_legacy_agent_tool_is_in_the_catalog_with_the_same_id_unless_removed_on_purpose() -> None:
    """Les agents existants référencent encore l'ancienne énumération : aucun identifiant ne change en silence."""
    for legacy in AgentTool:
        if legacy.value not in REMOVED_LEGACY_IDS:
            assert get_internal_tool(legacy.value) is not None, legacy


def test_removed_tools_are_not_in_the_catalog() -> None:
    assert all(get_internal_tool(tool_id) is None for tool_id in REMOVED_LEGACY_IDS)


def test_only_what_the_worker_can_run_is_offered() -> None:
    assert {tool.id for tool in available_internal_tools()} == {"calculatrice", "calcul_dates"}
    assert is_available("calculatrice")
    assert not is_available("base_connaissances")  # connu, pas encore exécutable
    assert not is_available("recherche_web")  # retiré


def test_the_dossier_reading_tools_are_not_a_choice() -> None:
    """Le worker les donne toujours à un agent : les proposer à cocher serait trompeur."""
    assert all(get_internal_tool(i) is None for i in ("recherche_dossier", "lecture_document", "search_documents"))


def test_only_tools_that_modify_data_ask_for_confirmation() -> None:
    assert {tool.id for tool in INTERNAL_TOOLS if tool.side_effect} == {"notes_internes", "propositions_analyse"}
