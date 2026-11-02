"""Les questions fréquentes d'une analyse : une liste de textes, versionnée comme le reste de l'analyse."""

import uuid

from fastapi.testclient import TestClient


def make_analyse(client: TestClient) -> str:
    return client.post("/api/analyses", json={"name": f"Questions {uuid.uuid4().hex[:6]}", "description": "T"}).json()[
        "id"
    ]


def url(analyse_id: str, suffix: str = "") -> str:
    return f"/api/analyses/{analyse_id}/frequent-questions{suffix}"


def test_an_analyse_starts_without_question_and_no_history(client: TestClient) -> None:
    assert client.get(url(make_analyse(client))).json() == {"questions": [], "versions": []}


def test_the_list_is_saved_in_order_and_the_previous_one_goes_to_the_history(client: TestClient) -> None:
    analyse_id = make_analyse(client)

    first = client.put(url(analyse_id), json={"questions": ["Quel est le loyer ?", "Qui est le bailleur ?"]}).json()
    second = client.put(url(analyse_id), json={"questions": ["Quel est le loyer ?"]}).json()

    assert first["questions"] == ["Quel est le loyer ?", "Qui est le bailleur ?"]
    assert [v["content"]["questions"] for v in first["versions"]] == [[]]
    assert second["questions"] == ["Quel est le loyer ?"]
    assert [v["content"]["questions"] for v in second["versions"]] == [
        ["Quel est le loyer ?", "Qui est le bailleur ?"],
        [],
    ]


def test_saving_the_same_list_adds_no_version(client: TestClient) -> None:
    analyse_id = make_analyse(client)
    client.put(url(analyse_id), json={"questions": ["Quel est le loyer ?"]})

    body = client.put(url(analyse_id), json={"questions": ["Quel est le loyer ?"]}).json()

    assert len(body["versions"]) == 1


def test_questions_are_cleaned_empty_ones_and_duplicates_are_dropped(client: TestClient) -> None:
    analyse_id = make_analyse(client)

    body = client.put(
        url(analyse_id),
        json={"questions": ["  Quel   est le loyer ? ", "", "   ", "quel est le LOYER ?", "Qui est le bailleur ?"]},
    ).json()

    assert body["questions"] == ["Quel est le loyer ?", "Qui est le bailleur ?"]


def test_a_question_that_is_too_long_is_refused(client: TestClient) -> None:
    response = client.put(url(make_analyse(client)), json={"questions": ["x" * 301]})

    assert response.status_code == 422


def test_there_is_no_limit_to_the_number_of_questions(client: TestClient) -> None:
    questions = [f"Question {index} ?" for index in range(120)]

    body = client.put(url(make_analyse(client)), json={"questions": questions}).json()

    assert body["questions"] == questions


def test_a_version_can_be_restored_and_the_current_list_becomes_a_version(client: TestClient) -> None:
    analyse_id = make_analyse(client)
    client.put(url(analyse_id), json={"questions": ["A ?"]})
    body = client.put(url(analyse_id), json={"questions": ["B ?"]}).json()
    first = next(v for v in body["versions"] if v["content"]["questions"] == ["A ?"])

    restored = client.post(url(analyse_id, f"/restore/{first['id']}")).json()

    assert restored["questions"] == ["A ?"]
    assert restored["versions"][0]["content"]["questions"] == ["B ?"]


def test_restoring_an_unknown_version_or_reading_an_unknown_analyse_answers_not_found(client: TestClient) -> None:
    analyse_id = make_analyse(client)

    assert client.post(url(analyse_id, f"/restore/{uuid.uuid4()}")).status_code == 404
    assert client.get(url(str(uuid.uuid4()))).status_code == 404
    assert client.put(url(str(uuid.uuid4())), json={"questions": []}).status_code == 404


def test_changing_the_questions_changes_the_version_of_the_analyse(client: TestClient) -> None:
    analyse_id = make_analyse(client)
    before = client.get(f"/api/analyses/{analyse_id}").json()["version"]

    client.put(url(analyse_id), json={"questions": ["Quel est le loyer ?"]})

    assert client.get(f"/api/analyses/{analyse_id}").json()["version"] != before
