"""Tests de la tâche d'extraction d'entités."""

import json

import httpx

from app import api_client
from app.llm import EntityValue, ExtractionResult
from app.tasks import extraction as extraction_mod
from app.tasks.extraction import extract_dossier_entities


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
        # Texte positionné des pages (page_id -> lignes) servi par /text-boxes, et bbox créées par le worker.
        self.text_boxes: dict[str, list[dict]] = {}
        self.bounding_boxes: list[dict] = []

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
        if path.endswith("/text-boxes"):
            return httpx.Response(200, json=self.text_boxes.get(path.split("/")[-2], []))
        if path.endswith("/bounding-boxes"):
            self.bounding_boxes.append({"page_id": path.split("/")[-2], **json.loads(request.content)})
            return httpx.Response(201, json={"id": f"bbox-{len(self.bounding_boxes)}"})
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


def test_extract_dossier_entities_deposits_entity_predictions(monkeypatch) -> None:
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
            return httpx.Response(200, json=_step_complete_response("step-extract", "extraction"))
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
    monkeypatch.setattr(
        extraction_mod.llm,
        "extract_entities_batch",
        lambda **kwargs: ExtractionResult(
            entities=[
                EntityValue(entity_name="nom", value="Dupont", confidence=0.95, page_numbers=[1]),
                EntityValue(
                    entity_name="adresse",
                    value="123 rue de Paris",
                    confidence=0.88,
                    page_numbers=[2],
                ),
            ]
        ),
    )

    extract_dossier_entities.run("dossier-1")

    assert len(prediction_bodies) == 2
    assert prediction_bodies[0]["kind"] == "entity"
    assert prediction_bodies[0]["name"] == "nom"
    assert prediction_bodies[0]["value"] == "Dupont"
    assert prediction_bodies[0]["entity_definition_id"] == "entity-nom"
    assert prediction_bodies[0]["page_ids"] == ["page-1"]
    assert prediction_bodies[1]["name"] == "adresse"
    assert prediction_bodies[1]["page_ids"] == ["page-2"]


def test_extract_dossier_entities_handles_no_entities(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/dossiers/dossier-1"):
            return httpx.Response(200, json=_make_dossier_response())
        if request.url.path.endswith("/analyses/analyse-1"):
            resp = _make_analyse_response()
            resp["extraction"]["entities"] = []
            return httpx.Response(200, json=resp)
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, json=_log_response())
        if request.url.path.endswith("/complete"):
            return httpx.Response(200, json=_step_complete_response("step-extract", "extraction"))
        return httpx.Response(404)

    monkeypatch.setattr(
        api_client,
        "get_client",
        lambda: httpx.Client(
            base_url="http://backend/api/internal",
            transport=httpx.MockTransport(handler),
        ),
    )

    extract_dossier_entities.run("dossier-1")


def _stub_extraction(monkeypatch, *, fail: bool = False) -> None:
    def extract(**kwargs):
        if fail:
            raise RuntimeError("LLM indisponible")
        return ExtractionResult(
            entities=[EntityValue(entity_name="nom", value="Dupont", confidence=0.9, page_numbers=[1])]
        )

    monkeypatch.setattr(extraction_mod.llm, "extract_entities_batch", extract)


def test_extraction_declares_one_unit_per_batch_and_attaches_predictions(monkeypatch) -> None:
    # Mode « legacy » : l'ancien découpage (lots de 5 pages sur tout le dossier).
    monkeypatch.setattr(extraction_mod.settings, "EXTRACTION_MODE", "legacy")
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_extraction(monkeypatch)

    extract_dossier_entities.run("dossier-1")

    # Le découpage en lots n'a pas changé : 2 pages, un seul lot (taille 5).
    assert len(backend.declared) == 1
    assert backend.declared[0]["kind"] == "extraction"
    assert backend.declared[0]["description"] == {"page_numbers": [1, 2], "page_ids": ["page-1", "page-2"]}
    assert [p["unit_id"] for p in backend.predictions] == ["unit-1"]
    assert backend.completed == [("unit-1", "terminé")]


def test_extraction_marks_the_unit_failed_and_still_raises(monkeypatch) -> None:
    backend = _UnitBackend()
    backend.install(monkeypatch)
    _stub_extraction(monkeypatch, fail=True)

    try:
        extract_dossier_entities.run("dossier-1")
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("L'erreur d'extraction doit remonter comme avant")

    assert backend.completed == [("unit-1", "échec")]


def test_extraction_works_without_analysis(monkeypatch) -> None:
    backend = _UnitBackend(with_analysis=False)
    backend.install(monkeypatch)
    _stub_extraction(monkeypatch)

    extract_dossier_entities.run("dossier-1")

    assert len(backend.predictions) == 1
    assert "unit_id" not in backend.predictions[0]


def _two_documents_dossier(pages_per_document: int = 2, content: str = "texte") -> dict:
    """Deux documents dont les pages portent les MÊMES numéros (1, 2...) : les
    numéros de page sont propres à chaque document."""
    dossier = _make_dossier_response()
    dossier["documents"] = [
        {
            "id": f"doc-{d}",
            "name": f"doc{d}.pdf",
            "pages": [
                {
                    "id": f"doc{d}-page-{n}",
                    "page_number": n,
                    "content": f"{content} d{d}p{n}",
                    "screenshot_key": None,
                }
                for n in range(1, pages_per_document + 1)
            ],
        }
        for d in (1, 2)
    ]
    return dossier


def _entity_defs(count: int) -> list[dict]:
    return [{"id": f"entity-{i}", "name": f"e{i}", "definition": f"d{i}", "type": "texte"} for i in range(count)]


class _RecordingLLM:
    """LLM d'extraction simulé : enregistre chaque appel et renvoie, pour
    chaque définition du groupe, une entité située sur la première page du lot."""

    def __init__(self, same_value: bool = False) -> None:
        self.calls: list[dict] = []
        self.same_value = same_value

    def __call__(self, **kwargs) -> ExtractionResult:
        pages = kwargs["pages"]
        names = [d["name"] for d in kwargs["entity_definitions"]]
        self.calls.append(
            {"pages": [p["page_number"] for p in pages], "definitions": names, "source": kwargs.get("source")}
        )
        return ExtractionResult(
            entities=[
                EntityValue(
                    entity_name=name,
                    value="valeur" if self.same_value else f"{name}@{pages[0]['page_number']}",
                    confidence=0.9,
                    page_numbers=[pages[0]["page_number"]],
                )
                for name in names
            ]
        )


def _setup_extraction(monkeypatch, backend: _UnitBackend, definitions: list[dict], **settings) -> _RecordingLLM:
    backend.install(monkeypatch)
    analyse = _make_analyse_response()
    analyse["extraction"]["entities"] = definitions
    original = backend.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/analyses/analyse-1"):
            return httpx.Response(200, json=analyse)
        return original(request)

    monkeypatch.setattr(
        api_client,
        "get_client",
        lambda: httpx.Client(base_url="http://backend/api/internal", transport=httpx.MockTransport(handler)),
    )
    llm = _RecordingLLM(same_value=settings.pop("same_value", False))
    monkeypatch.setattr(extraction_mod.llm, "extract_entities_batch", llm)
    monkeypatch.setattr(extraction_mod.settings, "EXTRACTION_MODE", "by_document")
    for name, value in settings.items():
        monkeypatch.setattr(extraction_mod.settings, name, value)
    return llm


def test_extraction_never_mixes_two_documents_in_a_lot(monkeypatch) -> None:
    backend = _UnitBackend(dossier=_two_documents_dossier())
    llm = _setup_extraction(monkeypatch, backend, _entity_defs(1), EXTRACTION_DEFINITIONS_PER_GROUP=8)

    extract_dossier_entities.run("dossier-1")

    # Un lot par document (2 pages chacun), jamais un lot de 4 pages.
    assert [c["pages"] for c in llm.calls] == [[1, 2], [1, 2]]
    assert [u["description"]["document_id"] for u in backend.declared] == ["doc-1", "doc-2"]
    assert [u["description"]["page_ids"] for u in backend.declared] == [
        ["doc1-page-1", "doc1-page-2"],
        ["doc2-page-1", "doc2-page-2"],
    ]


def test_the_source_of_each_document_reaches_the_llm_and_only_its_own(monkeypatch) -> None:
    dossier = _two_documents_dossier()
    dossier["documents"][0]["source"] = {"name": "Guichet", "description": "En main propre"}
    backend = _UnitBackend(dossier=dossier)
    llm = _setup_extraction(monkeypatch, backend, _entity_defs(1), EXTRACTION_DEFINITIONS_PER_GROUP=8)

    extract_dossier_entities.run("dossier-1")

    assert [c["source"] for c in llm.calls] == [{"name": "Guichet", "description": "En main propre"}, None]


def test_entities_are_attached_to_the_page_of_their_own_document(monkeypatch) -> None:
    """Les deux documents ont une page 1 : la prédiction du second ne doit pas
    être rattachée à la page 1 du premier (les numéros de page sont par document)."""
    backend = _UnitBackend(dossier=_two_documents_dossier())
    _setup_extraction(monkeypatch, backend, _entity_defs(1))
    page_posts: list[str] = []
    original = backend.handler

    def spy(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/predictions"):
            page_posts.append(request.url.path.split("/")[-2])
        return original(request)

    backend.handler = spy  # type: ignore[method-assign]
    backend.install(monkeypatch)
    analyse = _make_analyse_response()
    analyse["extraction"]["entities"] = _entity_defs(1)
    inner = backend.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/analyses/analyse-1"):
            return httpx.Response(200, json=analyse)
        return inner(request)

    monkeypatch.setattr(
        api_client,
        "get_client",
        lambda: httpx.Client(base_url="http://backend/api/internal", transport=httpx.MockTransport(handler)),
    )

    extract_dossier_entities.run("dossier-1")

    assert page_posts == ["doc1-page-1", "doc2-page-1"]


def test_definitions_are_split_into_fixed_size_groups_one_call_each(monkeypatch) -> None:
    backend = _UnitBackend(dossier=_two_documents_dossier(pages_per_document=1))
    llm = _setup_extraction(monkeypatch, backend, _entity_defs(5), EXTRACTION_DEFINITIONS_PER_GROUP=2)

    extract_dossier_entities.run("dossier-1")

    # 2 documents × 3 groupes (2 + 2 + 1 définitions).
    assert [c["definitions"] for c in llm.calls] == [["e0", "e1"], ["e2", "e3"], ["e4"]] * 2
    assert len(backend.declared) == 6
    assert [u["description"]["group"] for u in backend.declared] == [0, 1, 2, 0, 1, 2]
    assert backend.declared[0]["description"]["definition_ids"] == ["entity-0", "entity-1"]


def test_lots_follow_the_token_budget_with_overlap_and_duplicates_are_merged(monkeypatch) -> None:
    dossier = _two_documents_dossier(pages_per_document=4, content="m" * 800)
    dossier["documents"] = dossier["documents"][:1]
    backend = _UnitBackend(dossier=dossier)
    # Budget serré : ~2 pages par lot (chaque page ~200 jetons) ; recouvrement d'une page.
    llm = _setup_extraction(
        monkeypatch,
        backend,
        _entity_defs(1),
        EXTRACTION_MAX_TOKENS=2000,
        EXTRACTION_RESERVED_OUTPUT_TOKENS=1300,
        EXTRACTION_OVERLAP_PAGES=1,
        same_value=True,
    )

    extract_dossier_entities.run("dossier-1")

    assert len(llm.calls) > 1
    assert llm.calls[0]["pages"][-1] == llm.calls[1]["pages"][0]  # recouvrement
    assert {p for call in llm.calls for p in call["pages"]} == {1, 2, 3, 4}  # toutes les pages couvertes
    # Même définition et même valeur dans tous les lots : une seule entité déposée.
    assert len(backend.predictions) == 1
    # Mais chaque lot reste une unité (même sans entité), terminée.
    assert len(backend.declared) == len(llm.calls)
    assert len(backend.completed) == len(llm.calls)


def test_each_unit_carries_the_fingerprint_of_its_inputs(monkeypatch) -> None:
    backend = _UnitBackend(dossier=_two_documents_dossier())
    _setup_extraction(monkeypatch, backend, _entity_defs(1))

    extract_dossier_entities.run("dossier-1")

    fingerprints = [u["input_fingerprint"] for u in backend.declared]
    assert all(len(f) == 64 for f in fingerprints)
    # Deux documents au texte différent : deux empreintes différentes.
    assert fingerprints[0] != fingerprints[1]


def test_an_unchanged_unit_keeps_the_same_fingerprint_across_runs(monkeypatch) -> None:
    runs = []
    for _ in range(2):
        backend = _UnitBackend(dossier=_two_documents_dossier())
        _setup_extraction(monkeypatch, backend, _entity_defs(1))
        extract_dossier_entities.run("dossier-1")
        runs.append([u["input_fingerprint"] for u in backend.declared])
    assert runs[0] == runs[1]


def test_changing_one_document_only_changes_its_own_fingerprints(monkeypatch) -> None:
    before = _UnitBackend(dossier=_two_documents_dossier())
    _setup_extraction(monkeypatch, before, _entity_defs(1))
    extract_dossier_entities.run("dossier-1")

    changed = _two_documents_dossier()
    changed["documents"][1]["pages"][0]["content"] = "un texte différent"
    after = _UnitBackend(dossier=changed)
    _setup_extraction(monkeypatch, after, _entity_defs(1))
    extract_dossier_entities.run("dossier-1")

    old = [u["input_fingerprint"] for u in before.declared]
    new = [u["input_fingerprint"] for u in after.declared]
    assert new[0] == old[0]  # document inchangé : même empreinte
    assert new[1] != old[1]  # document modifié : recalcul


def test_changing_one_definition_only_changes_the_fingerprints_of_its_group(monkeypatch) -> None:
    definitions = _entity_defs(4)
    before = _UnitBackend(dossier=_two_documents_dossier(pages_per_document=1))
    _setup_extraction(monkeypatch, before, definitions, EXTRACTION_DEFINITIONS_PER_GROUP=2)
    extract_dossier_entities.run("dossier-1")

    edited = [dict(d) for d in definitions]
    edited[3]["definition"] = "nouvelle définition"
    after = _UnitBackend(dossier=_two_documents_dossier(pages_per_document=1))
    _setup_extraction(monkeypatch, after, edited, EXTRACTION_DEFINITIONS_PER_GROUP=2)
    extract_dossier_entities.run("dossier-1")

    old = [u["input_fingerprint"] for u in before.declared]
    new = [u["input_fingerprint"] for u in after.declared]
    # Par document : groupe 0 inchangé, groupe 1 (qui contient e3) modifié.
    assert [n == o for n, o in zip(new, old, strict=True)] == [True, False, True, False]


def test_legacy_mode_restores_the_previous_behaviour(monkeypatch) -> None:
    backend = _UnitBackend(dossier=_two_documents_dossier())
    llm = _setup_extraction(monkeypatch, backend, _entity_defs(5))
    monkeypatch.setattr(extraction_mod.settings, "EXTRACTION_MODE", "legacy")
    monkeypatch.setattr(extraction_mod.settings, "EXTRACTION_BATCH_SIZE", 3)

    extract_dossier_entities.run("dossier-1")

    # 4 pages au total, lots de 3 sur tout le dossier, toutes les définitions dans un seul appel.
    assert [len(c["pages"]) for c in llm.calls] == [3, 1]
    assert all(len(c["definitions"]) == 5 for c in llm.calls)
    assert all("group" not in u["description"] for u in backend.declared)
    # L'empreinte est calculée aussi dans ce mode.
    assert all(len(u["input_fingerprint"]) == 64 for u in backend.declared)


def test_reused_extraction_units_are_not_sent_to_the_llm(monkeypatch) -> None:
    backend = _UnitBackend(dossier=_two_documents_dossier())
    llm = _setup_extraction(monkeypatch, backend, _entity_defs(1))
    extract_dossier_entities.run("dossier-1")
    fingerprints = [u["input_fingerprint"] for u in backend.declared]
    assert len(llm.calls) == 2

    again = _UnitBackend(dossier=_two_documents_dossier())
    again.reuse = {fingerprints[0]: [{"name": "e0", "value": "e0@1"}]}  # le document 1 est inchangé
    llm_again = _setup_extraction(monkeypatch, again, _entity_defs(1))

    extract_dossier_entities.run("dossier-1")

    assert len(llm_again.calls) == 1  # seul le document 2 est recalculé
    assert [p["unit_id"] for p in again.predictions] == ["unit-2"]
    assert again.completed == [("unit-2", "terminé")]


def test_nothing_is_recomputed_when_every_extraction_unit_is_reused(monkeypatch) -> None:
    backend = _UnitBackend(dossier=_two_documents_dossier())
    _setup_extraction(monkeypatch, backend, _entity_defs(1))
    extract_dossier_entities.run("dossier-1")
    again = _UnitBackend(dossier=_two_documents_dossier())
    again.reuse = {u["input_fingerprint"]: [] for u in backend.declared}
    llm = _setup_extraction(monkeypatch, again, _entity_defs(1))

    extract_dossier_entities.run("dossier-1")

    assert llm.calls == [] and again.predictions == []


def test_reused_entities_seed_the_duplicate_merging_of_later_lots(monkeypatch) -> None:
    """Le premier lot d'un document est repris (pas d'appel) ; le LLM ne doit pas
    redéposer, dans le lot suivant (recouvrement), une entité que le lot repris contient déjà."""
    dossier = _two_documents_dossier(pages_per_document=4, content="m" * 800)
    dossier["documents"] = dossier["documents"][:1]
    settings = {"EXTRACTION_MAX_TOKENS": 2000, "EXTRACTION_RESERVED_OUTPUT_TOKENS": 1300, "EXTRACTION_OVERLAP_PAGES": 1}
    first = _UnitBackend(dossier=dossier)
    _setup_extraction(monkeypatch, first, _entity_defs(1), same_value=True, **settings)
    extract_dossier_entities.run("dossier-1")
    first_fingerprint = first.declared[0]["input_fingerprint"]
    assert len(first.predictions) == 1

    again = _UnitBackend(dossier=dossier)
    again.reuse = {first_fingerprint: [{"name": "e0", "value": "valeur"}]}
    llm = _setup_extraction(monkeypatch, again, _entity_defs(1), same_value=True, **settings)

    extract_dossier_entities.run("dossier-1")

    assert len(llm.calls) == len(first.declared) - 1  # le premier lot est repris
    assert again.predictions == []  # les lots suivants ne redéposent pas « valeur » : déjà dans le lot repris
