"""Tests de la tâche de classification."""

import json

import httpx

from app import api_client
from app.llm import ClassificationResult, LabelPrediction, MultiLabelClassificationResult
from app.storage import storage as storage_instance
from app.tasks import classification as classification_mod
from app.tasks.classification import classify_dossier


def _step_complete_response(step_id: str, kind: str) -> dict:
    return {
        "id": step_id,
        "kind": kind,
        "label": "",
        "status": "terminé",
        "started_at": "",
        "ended_at": "",
        "output": "",
        "logs": [],
    }


def _log_response() -> dict:
    return {"id": "log-1", "level": "info", "message": "ok", "created_at": ""}


def _make_dossier_response() -> dict:
    return {
        "id": "dossier-1",
        "analyse_id": "analyse-1",
        "status": "en_cours",
        "execution_steps": [
            {
                "id": "step-classif",
                "kind": "classification",
                "label": "Classification",
                "status": "en_cours",
            },
            {
                "id": "step-extract",
                "kind": "extraction",
                "label": "Extraction",
                "status": "en_cours",
            },
        ],
        "documents": [
            {
                "id": "doc-1",
                "name": "cni.pdf",
                "s3_key": "dossiers/x/cni.pdf",
                "mimetype": "application/pdf",
                "text_extraction_status": "terminé",
                "pages": [
                    {
                        "id": "page-1",
                        "page_number": 1,
                        "content": "Carte Nationale d'Identité\nNom: Dupont\nPrénom: Jean",
                        "screenshot_key": "screenshots/doc-1/page-1.png",
                    },
                    {
                        "id": "page-2",
                        "page_number": 2,
                        "content": "Adresse: 123 rue de Paris",
                        "screenshot_key": None,
                    },
                ],
            }
        ],
    }


def _make_analyse_response() -> dict:
    return {
        "id": "analyse-1",
        "classification": {
            "prompt": "Classifie ce document.",
            "labels": [
                {
                    "id": "label-cni",
                    "name": "CNI",
                    "definition": "Carte Nationale d'Identité",
                },
                {
                    "id": "label-passport",
                    "name": "Passeport",
                    "definition": "Passeport officiel",
                },
            ],
        },
        "extraction": {
            "prompt": "Extrais les entités.",
            "entities": [
                {
                    "id": "entity-nom",
                    "name": "nom",
                    "definition": "Nom de famille",
                    "type": "texte",
                },
                {
                    "id": "entity-adresse",
                    "name": "adresse",
                    "definition": "Adresse postale",
                    "type": "texte",
                },
            ],
        },
    }


class _UnitBackend:
    """Backend simulé qui accepte les unités de calcul et enregistre ce que le
    worker lui envoie."""

    def __init__(
        self, *, with_analysis: bool = True, units_unavailable: bool = False, dossier: dict | None = None
    ) -> None:
        self.dossier = dossier
        # Relance incrémentale (#119) : empreintes que le backend « reprend » de
        # l'analyse précédente, avec les entités reprises.
        self.reuse: dict[str, list[dict]] = {}
        self.with_analysis = with_analysis
        self.units_unavailable = units_unavailable
        self.declared: list[dict] = []
        self.completed: list[tuple[str, str]] = []
        self.predictions: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/dossiers/dossier-1"):
            return httpx.Response(200, json=self.dossier or _make_dossier_response())
        if path.endswith("/analyses/analyse-1"):
            return httpx.Response(200, json=_make_analyse_response())
        if path.endswith("/analysis-units"):
            if self.units_unavailable:
                return httpx.Response(500)
            if not self.with_analysis:
                return httpx.Response(404)
            self.declared.append(json.loads(request.content))
            fingerprint = self.declared[-1].get("input_fingerprint")
            payload = {"id": f"unit-{len(self.declared)}", "analysis_id": "analysis-1"}
            if fingerprint in self.reuse:
                payload |= {"reused": True, "reused_entities": self.reuse[fingerprint]}
            return httpx.Response(201, json=payload)
        if "/analysis-units/" in path and path.endswith("/complete"):
            self.completed.append((path.split("/")[-2], json.loads(request.content)["status"]))
            return httpx.Response(200, json={"id": path.split("/")[-2], "analysis_id": "analysis-1"})
        if path.endswith("/logs"):
            return httpx.Response(200, json=_log_response())
        if path.endswith("/complete"):
            return httpx.Response(200, json=_step_complete_response("step", "classification"))
        if path.endswith("/predictions"):
            self.predictions.append(json.loads(request.content))
            return httpx.Response(201, json={"id": "pred", **self.predictions[-1]})
        return httpx.Response(404)

    def install(self, monkeypatch) -> None:
        monkeypatch.setattr(
            api_client,
            "get_client",
            lambda: httpx.Client(base_url="http://backend/api/internal", transport=httpx.MockTransport(self.handler)),
        )


def test_classify_dossier_deposits_label_predictions(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    prediction_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/dossiers/dossier-1"):
            return httpx.Response(200, json=_make_dossier_response())
        if request.url.path.endswith("/analyses/analyse-1"):
            return httpx.Response(200, json=_make_analyse_response())
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, json=_log_response())
        if request.url.path.endswith("/complete"):
            return httpx.Response(200, json=_step_complete_response("step-classif", "classification"))
        if request.url.path.endswith("/predictions"):
            prediction_bodies.append(json.loads(request.content))
            return httpx.Response(201, json={"id": "pred-1", **prediction_bodies[-1]})
        return httpx.Response(404)

    monkeypatch.setattr(
        api_client,
        "get_client",
        lambda: httpx.Client(
            base_url="http://backend/api/internal",
            transport=httpx.MockTransport(handler),
        ),
    )
    monkeypatch.setattr(storage_instance, "get_object", lambda key: b"fake-png-bytes")
    monkeypatch.setattr(
        classification_mod.llm,
        "describe_page_image",
        lambda image_bytes: "Photo d'identité visible, type CNI",
    )
    monkeypatch.setattr(
        classification_mod.llm,
        "classify_page",
        lambda **kwargs: ClassificationResult(
            prediction=LabelPrediction(label_name="CNI", confidence=0.95, reasoning="Photo visible")
        ),
    )

    classify_dossier.run("dossier-1")

    # Two pages classified
    assert len(prediction_bodies) == 2
    assert prediction_bodies[0]["kind"] == "label"
    assert prediction_bodies[0]["name"] == "CNI"
    assert prediction_bodies[0]["label_definition_id"] == "label-cni"
    assert prediction_bodies[0]["confidence"] == 0.95
    # Step completed
    assert any(path.endswith("/complete") for _, path in calls)


def test_classify_dossier_multi_label_deposits_one_prediction_per_label(monkeypatch) -> None:
    prediction_bodies: list[dict] = []
    llm_kwargs: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/dossiers/dossier-1"):
            return httpx.Response(200, json=_make_dossier_response())
        if request.url.path.endswith("/analyses/analyse-1"):
            resp = _make_analyse_response()
            resp["classification"]["multi_label"] = True
            return httpx.Response(200, json=resp)
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, json=_log_response())
        if request.url.path.endswith("/complete"):
            return httpx.Response(200, json=_step_complete_response("step-classif", "classification"))
        if request.url.path.endswith("/predictions"):
            prediction_bodies.append(json.loads(request.content))
            return httpx.Response(201, json={"id": "pred-1", **prediction_bodies[-1]})
        return httpx.Response(404)

    def classify(**kwargs):
        llm_kwargs.append(kwargs)
        return MultiLabelClassificationResult(
            predictions=[
                LabelPrediction(label_name="CNI", confidence=0.9),
                LabelPrediction(label_name="Passeport", confidence=0.7),
                LabelPrediction(label_name="CNI", confidence=0.5),  # doublon ignoré
            ]
        )

    monkeypatch.setattr(
        api_client,
        "get_client",
        lambda: httpx.Client(base_url="http://backend/api/internal", transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(storage_instance, "get_object", lambda key: b"fake-png-bytes")
    monkeypatch.setattr(classification_mod.llm, "describe_page_image", lambda image_bytes: "desc")
    monkeypatch.setattr(classification_mod.llm, "classify_page", classify)

    classify_dossier.run("dossier-1")

    assert all(kwargs["multi_label"] is True for kwargs in llm_kwargs)
    # Deux pages x deux labels distincts.
    assert [b["name"] for b in prediction_bodies] == ["CNI", "Passeport"] * 2


def test_classify_dossier_handles_no_labels(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/dossiers/dossier-1"):
            return httpx.Response(200, json=_make_dossier_response())
        if request.url.path.endswith("/analyses/analyse-1"):
            resp = _make_analyse_response()
            resp["classification"]["labels"] = []
            return httpx.Response(200, json=resp)
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, json=_log_response())
        if request.url.path.endswith("/complete"):
            return httpx.Response(200, json=_step_complete_response("step-classif", "classification"))
        return httpx.Response(404)

    monkeypatch.setattr(
        api_client,
        "get_client",
        lambda: httpx.Client(
            base_url="http://backend/api/internal",
            transport=httpx.MockTransport(handler),
        ),
    )

    classify_dossier.run("dossier-1")


def _stub_classification(monkeypatch, *, fail_on_page: int | None = None) -> None:
    monkeypatch.setattr(storage_instance, "get_object", lambda key: b"png")
    monkeypatch.setattr(classification_mod.llm, "describe_page_image", lambda image_bytes: "desc")
    seen = {"count": 0}

    def classify(**kwargs):
        seen["count"] += 1
        if fail_on_page is not None and seen["count"] == fail_on_page:
            raise RuntimeError("LLM indisponible")
        return ClassificationResult(prediction=LabelPrediction(label_name="CNI", confidence=0.9, reasoning="r"))

    monkeypatch.setattr(classification_mod.llm, "classify_page", classify)


def test_classification_declares_one_unit_per_page_and_attaches_predictions(monkeypatch) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_classification(monkeypatch)

    classify_dossier.run("dossier-1")

    assert [u["kind"] for u in backend.declared] == ["classification", "classification"]
    assert [u["description"]["page_number"] for u in backend.declared] == [1, 2]
    assert backend.declared[0]["description"]["page_id"] == "page-1"
    assert backend.declared[0]["description"]["document_id"] == "doc-1"
    assert [p["unit_id"] for p in backend.predictions] == ["unit-1", "unit-2"]
    assert backend.completed == [("unit-1", "terminé"), ("unit-2", "terminé")]


def test_classification_marks_the_unit_failed_when_the_page_fails(monkeypatch) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_classification(monkeypatch, fail_on_page=2)

    try:
        classify_dossier.run("dossier-1")
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("L'erreur de classification doit remonter comme avant")

    assert backend.completed == [("unit-1", "terminé"), ("unit-2", "échec")]


def test_classification_works_without_analysis(monkeypatch) -> None:
    """Dossier sans analyse (exécution démarrée avant #125) : le backend répond
    404 aux unités, le worker dépose les prédictions comme avant."""
    backend = _UnitBackend(with_analysis=False)
    backend.install(monkeypatch)
    _stub_classification(monkeypatch)

    classify_dossier.run("dossier-1")

    assert len(backend.predictions) == 2
    assert all("unit_id" not in p for p in backend.predictions)
    assert backend.completed == []


def test_classification_survives_a_broken_unit_api(monkeypatch) -> None:
    backend = _UnitBackend(units_unavailable=True)
    backend.install(monkeypatch)
    _stub_classification(monkeypatch)

    classify_dossier.run("dossier-1")

    assert len(backend.predictions) == 2
    assert all("unit_id" not in p for p in backend.predictions)


def test_classification_units_carry_a_fingerprint(monkeypatch) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_classification(monkeypatch)

    classify_dossier.run("dossier-1")

    fingerprints = [u["input_fingerprint"] for u in backend.declared]
    assert len(fingerprints) == 2 and fingerprints[0] != fingerprints[1]


def test_reused_classification_units_call_neither_vlm_nor_llm(monkeypatch) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    # Première passe pour connaître les empreintes des deux pages.
    _stub_classification(monkeypatch)
    classify_dossier.run("dossier-1")
    fingerprints = [u["input_fingerprint"] for u in backend.declared]

    again = _UnitBackend()
    again.reuse = {fp: [] for fp in fingerprints}
    again.install(monkeypatch)
    calls = {"vlm": 0, "llm": 0}
    monkeypatch.setattr(classification_mod.llm, "describe_page_image", lambda image_bytes: calls.__setitem__("vlm", 1))
    monkeypatch.setattr(classification_mod.llm, "classify_page", lambda **kwargs: calls.__setitem__("llm", 1))

    classify_dossier.run("dossier-1")

    assert calls == {"vlm": 0, "llm": 0}  # aucun appel : tout est repris
    assert len(again.declared) == 2  # les unités sont tout de même déclarées (c'est ce qui les fait reprendre)
    assert again.predictions == []
    assert again.completed == []  # une unité reprise est déjà terminée côté backend


def test_only_the_changed_classification_unit_is_computed(monkeypatch) -> None:
    first = _UnitBackend()
    first.install(monkeypatch)
    _stub_classification(monkeypatch)
    classify_dossier.run("dossier-1")
    fingerprints = [u["input_fingerprint"] for u in first.declared]

    again = _UnitBackend()
    again.reuse = {fingerprints[0]: []}  # la page 1 est inchangée, la page 2 non
    again.install(monkeypatch)
    _stub_classification(monkeypatch)

    classify_dossier.run("dossier-1")

    assert [p["name"] for p in again.predictions] == ["CNI"]  # une seule page recalculée
    assert [p["unit_id"] for p in again.predictions] == ["unit-2"]
    assert again.completed == [("unit-2", "terminé")]
