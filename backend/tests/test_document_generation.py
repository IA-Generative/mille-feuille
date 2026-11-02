"""Tests de la génération des valeurs de champs (issue #141) : le prompt versionné, le déclenchement et le suivi de la
génération, ce que l'agent lit (le contexte) et ce qu'il dépose (le LLM est simulé, la base est réelle)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from document_helpers import add_entity, by_name, create_draft, entity, field, make_dossier, make_template, run, url
from fastapi.testclient import TestClient

from app.agent.document_generation import FieldProposal, GeneratedFields
from app.core.security.factory import RequestContext, get_current_user
from app.main import app
from app.models.document_draft import DocumentDraft

PROMPT = "/api/admin/generation-prompt"


@pytest.fixture
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    calls: list[tuple] = []
    monkeypatch.setattr(
        "app.routers.document_drafts.dispatch_document_generation",
        lambda draft_id, names=None, instruction=None: calls.append((draft_id, names, instruction)),
    )
    return calls


@pytest.fixture
def setup(client: TestClient) -> dict[str, Any]:
    dossier_id, analysis = make_dossier(client)
    add_entity(client, analysis, "nom", "Dupont")
    template_id = make_template(
        client,
        [
            field("nom", entity("nom")),
            field("decision", instruction="Une phrase"),
            field("motif"),
            field("dossier", {"kind": "dossier_metadata", "key": "dossier_name"}),
        ],
        dossier_id=dossier_id,
    )
    draft = create_draft(client, dossier_id, template_id)
    return {"dossier_id": dossier_id, "analysis": analysis, "draft": draft, "base": url(dossier_id, draft["id"])}


def draft_row(client: TestClient, draft_id: str) -> DocumentDraft:
    return run(client, lambda s: s.get(DocumentDraft, uuid.UUID(draft_id)))


# --- Prompt versionné ---


def test_the_default_prompt_applies_until_a_version_exists(client: TestClient) -> None:
    from app.services import generation_prompt

    # La base garde les versions des exécutions précédentes : on vérifie le défaut au niveau du service.
    assert generation_prompt.version_label(None) == "défaut"
    assert generation_prompt.version_label(3) == "doc-fields-v3"
    assert "Respecte le type du champ" in generation_prompt.DEFAULT_PROMPT

    current = client.get(PROMPT).json()
    assert set(current) == {"version_number", "label", "content", "is_default"}
    assert current["is_default"] is (current["version_number"] is None)


def test_a_prompt_edit_adds_a_version_and_restore_adds_another(client: TestClient) -> None:
    first = client.post(f"{PROMPT}/versions", json={"content": "Prompt de test numéro un, assez long."})
    second = client.post(f"{PROMPT}/versions", json={"content": "Prompt de test numéro deux, assez long."})
    assert first.status_code == second.status_code == 201
    assert second.json()["version_number"] == first.json()["version_number"] + 1

    current = client.get(PROMPT).json()
    assert current["content"].startswith("Prompt de test numéro deux") and current["is_default"] is False
    assert current["label"] == f"doc-fields-v{second.json()['version_number']}"

    restored = client.post(f"{PROMPT}/restore", json={"version_id": first.json()["id"]})
    assert restored.status_code == 201
    assert restored.json()["content"].startswith("Prompt de test numéro un")
    assert restored.json()["restored_from_version_id"] == first.json()["id"]
    assert restored.json()["version_number"] == second.json()["version_number"] + 1
    # Rien n'est écrasé : les anciennes versions sont toujours là, inchangées.
    contents = {v["id"]: v["content"] for v in client.get(f"{PROMPT}/versions").json()}
    assert contents[second.json()["id"]].startswith("Prompt de test numéro deux")
    assert client.get(PROMPT).json()["version_number"] == restored.json()["version_number"]


def test_a_too_short_prompt_and_an_unknown_version_are_refused(client: TestClient) -> None:
    assert client.post(f"{PROMPT}/versions", json={"content": "court"}).status_code == 422
    assert client.post(f"{PROMPT}/restore", json={"version_id": str(uuid.uuid4())}).status_code == 404


def test_simultaneous_prompt_edits_get_distinct_numbers(client: TestClient) -> None:
    import asyncio

    from app.db import async_session_factory
    from app.services import generation_prompt

    async def write(i: int) -> int:
        async with async_session_factory() as session:
            return (
                await generation_prompt.add_version(session, content=f"Version simultanée {i} " * 3, author_id="a")
            ).version_number

    async def many() -> list[int]:
        return list(await asyncio.gather(*(write(i) for i in range(5))))

    numbers = client.portal.call(many)
    assert len(set(numbers)) == 5 and max(numbers) - min(numbers) == 4


def test_the_prompt_routes_are_admin_only(client: TestClient) -> None:
    def as_non_admin() -> RequestContext:
        return RequestContext(user_id="regular", email="r@example.com", roles=[], is_admin=False)

    app.dependency_overrides[get_current_user] = as_non_admin
    try:
        calls = [
            client.get(PROMPT),
            client.get(f"{PROMPT}/versions"),
            client.post(f"{PROMPT}/versions", json={"content": "x" * 30}),
            client.post(f"{PROMPT}/restore", json={"version_id": str(uuid.uuid4())}),
        ]
        assert [c.status_code for c in calls] == [403] * 4
    finally:
        del app.dependency_overrides[get_current_user]


# --- Déclenchement ---


def test_generating_dispatches_the_task_and_tracks_it_on_the_draft(client: TestClient, setup: dict, dispatched) -> None:
    response = client.post(setup["base"] + "/generate", json={})

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["generation_status"] == "en_cours" and body["generation_requested_at"]
    # Seuls les champs à générer : ni la métadonnée du dossier (un fait), pas de champ validé.
    assert dispatched == [(setup["draft"]["id"], None, None)]
    assert draft_row(client, setup["draft"]["id"]).generation_requested_by


def test_a_second_generation_is_refused_while_one_runs(client: TestClient, setup: dict, dispatched) -> None:
    assert client.post(setup["base"] + "/generate", json={}).status_code == 202
    assert client.post(setup["base"] + "/generate", json={}).status_code == 409
    assert client.post(setup["base"] + "/fields/decision/regenerate", json={}).status_code == 409
    assert len(dispatched) == 1


def test_a_lost_generation_can_be_restarted_after_a_while(client: TestClient, setup: dict, dispatched) -> None:
    client.post(setup["base"] + "/generate", json={})

    async def age(session: Any) -> None:
        row = await session.get(DocumentDraft, uuid.UUID(setup["draft"]["id"]))
        row.generation_requested_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

    run(client, age)
    assert client.post(setup["base"] + "/generate", json={}).status_code == 202
    assert len(dispatched) == 2


def test_generating_some_fields_and_validating_the_rest(client: TestClient, setup: dict, dispatched) -> None:
    client.put(setup["base"] + "/fields/decision", json={"value": "Accordée"})
    assert client.post(setup["base"] + "/generate", json={"names": ["decision"]}).status_code == 409
    assert dispatched == []  # le seul champ demandé est validé : rien à générer, rien n'est lancé

    response = client.post(setup["base"] + "/generate", json={"names": ["motif", "motif", "dossier"]})
    assert response.status_code == 202
    assert dispatched == [(setup["draft"]["id"], ["motif"], None)]  # dédoublonné, sans la métadonnée


def test_generation_skips_validated_fields_but_the_task_gets_no_name_filter(
    client: TestClient, setup: dict, dispatched
) -> None:
    client.put(setup["base"] + "/fields/decision", json={"value": "Accordée"})
    assert client.post(setup["base"] + "/generate", json={}).status_code == 202
    assert dispatched[0][1] is None  # le worker écarte lui aussi les champs validés


def test_nothing_to_generate_when_everything_is_validated(client: TestClient, setup: dict, dispatched) -> None:
    for name, value in (("decision", "Accordée"), ("motif", "Dossier complet")):
        client.put(setup["base"] + f"/fields/{name}", json={"value": value})
    client.post(setup["base"] + "/fields/nom/validate")
    response = client.post(setup["base"] + "/generate", json={})
    assert response.status_code == 409 and "jamais réécrits" in response.json()["detail"]
    assert dispatched == [] and client.get(setup["base"]).json()["generation_status"] is None


def test_unknown_field_and_archived_draft(client: TestClient, setup: dict, dispatched) -> None:
    assert client.post(setup["base"] + "/generate", json={"names": ["inconnu"]}).status_code == 404
    assert client.post(setup["base"] + "/fields/inconnu/regenerate", json={}).status_code == 404
    client.post(setup["base"] + "/archive")
    assert client.post(setup["base"] + "/generate", json={}).status_code == 409
    assert dispatched == []


def test_regenerating_one_field_with_an_instruction(client: TestClient, setup: dict, dispatched) -> None:
    response = client.post(setup["base"] + "/fields/decision/regenerate", json={"instruction": "  Plus court  "})
    assert response.status_code == 202
    assert dispatched == [(setup["draft"]["id"], ["decision"], "Plus court")]


def test_a_validated_field_cannot_be_regenerated(client: TestClient, setup: dict, dispatched) -> None:
    client.put(setup["base"] + "/fields/decision", json={"value": "Accordée"})
    response = client.post(setup["base"] + "/fields/decision/regenerate", json={"instruction": "Autre"})
    assert response.status_code == 409 and "modifiez-le à la main" in response.json()["detail"]
    assert dispatched == []


# --- Ce que l'agent lit, ce qu'il dépose ---


def draft_context(client: TestClient, setup: dict) -> dict:
    """Le contexte de génération tel que l'agent le lit."""
    from app.db import async_session_factory
    from app.services.draft_generation_context import build_draft_context

    async def read() -> dict:
        async with async_session_factory() as db:
            draft = await db.get(DocumentDraft, uuid.UUID(setup["draft"]["id"]))
            return (await build_draft_context(db, draft)).model_dump(mode="json")

    return client.portal.call(read)


def generate(client: TestClient, setup: dict, proposals: list, *, names=None, instruction=None, draft_id=None):  # noqa: ANN001, ANN201
    """Lance le travail de génération, le LLM répondant `proposals` (des FieldProposal, ou une exception)."""
    from app.agent import llm
    from app.agent.jobs.document_fields import generate_document_fields

    async def fake(messages: list) -> Any:
        fake.messages.append(messages)
        if isinstance(proposals, Exception):
            raise proposals
        return GeneratedFields(fields=proposals)

    fake.messages = []  # type: ignore[attr-defined]
    original = llm.generate_field_values
    llm.generate_field_values = fake
    try:
        client.portal.call(generate_document_fields, draft_id or setup["draft"]["id"], names, instruction)
    finally:
        llm.generate_field_values = original
    return fake.messages


def test_the_context_has_everything_the_agent_needs(client: TestClient, setup: dict) -> None:
    client.post(f"/api/dossiers/{setup['dossier_id']}/notes", json={"content": "Pièce vérifiée par téléphone"})
    archived = client.post(f"/api/dossiers/{setup['dossier_id']}/notes", json={"content": "Note archivée"}).json()
    client.post(f"/api/dossiers/{setup['dossier_id']}/notes/{archived['id']}/archive")

    body = draft_context(client, setup)

    assert body["draft_id"] == setup["draft"]["id"] and body["status"] == "brouillon"
    assert [f["name"] for f in body["fields"]] == ["nom", "decision", "motif", "dossier"]
    decision = body["fields"][1]
    assert (
        decision["instruction"] == "Une phrase" and decision["status"] == "non_renseigné" and decision["value"] is None
    )
    assert body["fields"][0]["status"] == "proposé" and body["fields"][0]["value"] == "Dupont"
    assert [(e["kind"], e["name"], e["text"]) for e in body["elements"]] == [("entity", "nom", "Dupont")]
    assert [n["content"] for n in body["notes"]] == ["Pièce vérifiée par téléphone"]  # pas la note archivée
    assert body["metadata"]["dossier_name"].startswith("Dossier ")
    assert body["prompt"] and body["prompt_label"]


def test_the_context_reads_the_frozen_revision_not_the_current_analysis(client: TestClient, setup: dict) -> None:
    add_entity(client, setup["analysis"], "adresse", "Ajoutée après le brouillon")
    body = draft_context(client, setup)
    assert [e["name"] for e in body["elements"]] == ["nom"]


def test_the_context_carries_the_prompt_in_force(client: TestClient, setup: dict) -> None:
    created = client.post(f"{PROMPT}/versions", json={"content": "Prompt versionné du contexte, assez long."}).json()
    body = draft_context(client, setup)
    assert body["prompt"].startswith("Prompt versionné du contexte")
    assert body["prompt_version_number"] == created["version_number"]
    assert body["prompt_label"] == f"doc-fields-v{created['version_number']}"


def test_the_agent_proposes_a_value_with_its_traces(client: TestClient, setup: dict) -> None:
    messages = generate(
        client,
        setup,
        [
            FieldProposal(name="decision", found=True, value="Demande accordée", source_ids=["E1"]),
            FieldProposal(name="motif", found=False),
        ],
    )

    # Le LLM reçoit le prompt versionné et le contexte borné.
    assert messages[0][0]["role"] == "system" and "decision" in messages[0][1]["content"]
    decision = by_name(client.get(setup["base"]).json())["decision"]["current"]
    assert (decision["status"], decision["origin"], decision["value"]) == ("proposé", "agent", "Demande accordée")
    assert decision["prompt_version"].startswith("doc-fields-v") and decision["model"]
    assert [s["type"] for s in decision["sources"]] == ["analysis_element"]
    events = client.get(setup["base"] + "/events", params={"field": "decision"}).json()
    assert events[-1]["kind"] == "proposed" and events[-1]["prompt_version"] == decision["prompt_version"]
    # Un champ introuvable reste « non renseigné » : jamais inventé.
    assert by_name(client.get(setup["base"]).json())["motif"]["current"]["status"] == "non_renseigné"


def test_the_end_of_a_generation_is_reported_on_the_draft(client: TestClient, setup: dict, dispatched) -> None:
    client.post(setup["base"] + "/generate", json={})

    generate(
        client,
        setup,
        [
            FieldProposal(name="nom", found=True, value="Dupont"),
            FieldProposal(name="decision", found=True, value="Accordée"),
            FieldProposal(name="motif", found=False),
        ],
    )

    body = client.get(setup["base"]).json()
    assert body["generation_status"] == "terminé" and body["generation_proposal_count"] == 2
    assert body["generation_missing"] == ["motif"] and body["generation_truncated"] is False
    assert body["generation_prompt_version"].startswith("doc-fields-v") and body["generation_error"] is None
    # La génération est terminée : on peut en relancer une.
    assert client.post(setup["base"] + "/generate", json={}).status_code == 202


def test_a_regeneration_is_journaled_with_its_instruction(client: TestClient, setup: dict) -> None:
    generate(client, setup, [FieldProposal(name="decision", found=True, value="Première version")])
    generate(
        client,
        setup,
        [FieldProposal(name="decision", found=True, value="Version courte")],
        names=["decision"],
        instruction="Plus court",
    )

    events = client.get(setup["base"] + "/events", params={"field": "decision"}).json()
    assert [e["kind"] for e in events] == ["proposed", "regenerated"] and events[-1]["detail"] == "Plus court"
    assert by_name(client.get(setup["base"]).json())["decision"]["current"]["value"] == "Version courte"


def test_the_agent_can_never_rewrite_a_validated_value(client: TestClient, setup: dict) -> None:
    client.put(setup["base"] + "/fields/decision", json={"value": "Saisie à la main"})

    messages = generate(
        client,
        setup,
        [
            FieldProposal(name="decision", found=True, value="Écrasée"),
            FieldProposal(name="dossier", found=True, value="X"),  # une métadonnée du dossier, validée d'office
            FieldProposal(name="motif", found=True, value="Un motif"),
        ],
    )

    fields = by_name(client.get(setup["base"]).json())
    assert fields["decision"]["current"]["value"] == "Saisie à la main"
    assert fields["dossier"]["current"]["value"] != "X"
    assert fields["motif"]["current"]["value"] == "Un motif"
    # Les champs validés ne sont même pas demandés au modèle.
    assert "decision" not in messages[0][1]["content"].split("--- Champs à renseigner ---")[1].split("---")[0]


def test_the_agent_proposal_must_match_the_field_type(client: TestClient, setup: dict) -> None:
    template_id = make_template(client, [field("montant", type="number")], dossier_id=setup["dossier_id"])
    draft = create_draft(client, setup["dossier_id"], template_id)
    other = {**setup, "draft": draft, "base": url(setup["dossier_id"], draft["id"])}

    generate(client, other, [FieldProposal(name="montant", found=True, value="beaucoup")])
    body = client.get(other["base"]).json()
    assert body["generation_missing"] == ["montant"] and body["generation_proposal_count"] == 0

    generate(client, other, [FieldProposal(name="montant", found=True, value="1 250,5")])
    assert by_name(client.get(other["base"]).json())["montant"]["current"]["value"] == 1250.5


def test_a_failed_generation_keeps_its_reason(client: TestClient, setup: dict, dispatched) -> None:
    client.post(setup["base"] + "/generate", json={})

    generate(client, setup, RuntimeError("LLM injoignable"))

    body = client.get(setup["base"]).json()
    assert body["generation_status"] == "échec" and body["generation_error"] == "LLM injoignable"


def test_an_unknown_draft_is_ignored(client: TestClient, setup: dict) -> None:
    messages = generate(client, setup, [], draft_id=str(uuid.uuid4()))
    assert messages == []
