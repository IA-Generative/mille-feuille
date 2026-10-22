from fastapi.testclient import TestClient

from tests.test_chat_tool_calls import INTERNAL, chat, messages
from tests.test_chat_tool_calls import dispatched as dispatched  # noqa: F401  (fixture autouse du module d'origine)


def external(number: int, **extra) -> dict:
    return {
        "source_id": f"p-{number}",
        "kind": "document",
        "title": "Guide.pdf",
        "url": "https://kb.example.gouv.fr/doc/d-1?page=14",
        "preview_url": "https://kb.example.gouv.fr/doc/d-1/14.png",
        "page": 14,
        "boxes": [{"page": 14, "x_min": 0.1, "y_min": 0.2, "x_max": 0.9, "y_max": 0.3}],
        "passage": "Un RIB est exigé.",
        "score": 0.91,
        "collection_id": "guide",
        "collection_name": "Guide des subventions",
        "source_name": "Références",
    } | extra


def deposit(client: TestClient, conversation_id: str, sources: list[dict]):
    return client.post(
        f"/api/internal/conversations/{conversation_id}/messages",
        json={"content": "Un RIB est exigé [1].", "external_sources": sources},
        headers=INTERNAL,
    )


def test_the_sources_of_the_knowledge_base_come_with_the_message_in_order(client: TestClient) -> None:
    dossier_id, conversation_id = chat(client)
    web = external(2, kind="web", title="Service-Public", page=None, preview_url=None, boxes=[])

    response = deposit(client, conversation_id, [external(1), web])

    assert response.status_code == 200, response.text
    assert [s["source_id"] for s in response.json()["external_sources"]] == ["p-1", "p-2"]
    [message] = [m for m in messages(client, dossier_id, conversation_id) if m["role"] == "assistant"]
    first, second = message["external_sources"]
    assert (first["position"], first["title"], first["page"]) == (0, "Guide.pdf", 14)
    assert first["boxes"] == [{"page": 14, "x_min": 0.1, "y_min": 0.2, "x_max": 0.9, "y_max": 0.3}]
    assert first["preview_url"] == "https://kb.example.gouv.fr/doc/d-1/14.png"
    assert (second["kind"], second["page"], second["preview_url"], second["boxes"]) == ("web", None, None, [])


def test_a_message_without_external_sources_has_an_empty_list(client: TestClient) -> None:
    dossier_id, conversation_id = chat(client)

    deposit(client, conversation_id, [])

    [message] = [m for m in messages(client, dossier_id, conversation_id) if m["role"] == "assistant"]
    assert message["external_sources"] == []


def test_a_deposit_is_checked_like_the_contract(client: TestClient) -> None:
    _, conversation_id = chat(client)

    bad_box = external(1, boxes=[{"page": 1, "x_min": 0.1, "y_min": 0.1, "x_max": 1.4, "y_max": 0.2}])
    assert deposit(client, conversation_id, [bad_box]).status_code == 422
    assert deposit(client, conversation_id, [external(1, kind="pdf")]).status_code == 422
    assert deposit(client, conversation_id, [external(1, score=2)]).status_code == 422
    assert deposit(client, conversation_id, [external(n) for n in range(11)]).status_code == 422  # 10 au plus
