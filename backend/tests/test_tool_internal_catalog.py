from app.models.analyse import AgentTool
from app.services.tools.internal_catalog import INTERNAL_TOOLS, get_internal_tool


def test_ids_are_unique() -> None:
    ids = [tool.id for tool in INTERNAL_TOOLS]
    assert len(ids) == len(set(ids))


def test_every_legacy_agent_tool_is_in_the_catalog_with_the_same_id() -> None:
    """Les agents existants référencent encore l'ancienne énumération : aucun identifiant ne doit changer."""
    for legacy in AgentTool:
        assert get_internal_tool(legacy.value) is not None, legacy


def test_only_tools_that_modify_data_ask_for_confirmation() -> None:
    assert {tool.id for tool in INTERNAL_TOOLS if tool.side_effect} == {"notes_internes", "propositions_analyse"}


def test_knowledge_base_asks_for_a_per_analysis_configuration() -> None:
    assert get_internal_tool("base_connaissances").config == "collections"
    assert get_internal_tool("inconnu") is None
