"""Zones des entités dans le résultat d'extraction éphémère (sans base de données : on passe des objets simples)."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.models.document_page import PredictionKind, PredictionSource
from app.models.dossier import DossierStatus
from app.services.ephemeral_results import to_extraction_out


def _box(page_id: uuid.UUID, x_min: float) -> SimpleNamespace:
    return SimpleNamespace(document_page_id=page_id, x_min=x_min, y_min=0.1, x_max=x_min + 0.2, y_max=0.12)


def test_each_page_of_a_multi_page_entity_only_gets_its_own_boxes() -> None:
    page_1, page_2 = uuid.uuid4(), uuid.uuid4()
    prediction = SimpleNamespace(
        id=uuid.uuid4(),
        kind=PredictionKind.ENTITY,
        name="nom",
        value="Dupont",
        confidence=0.9,
        source=PredictionSource.GLINER,
        bounding_boxes=[_box(page_1, 0.3), _box(page_2, 0.5)],
    )
    run = SimpleNamespace(
        id=uuid.uuid4(),
        status=DossierStatus.TERMINE,
        execution_steps=[],
        expires_at=datetime.now(UTC),
        documents=[
            SimpleNamespace(
                name="cni.pdf",
                pages=[
                    SimpleNamespace(id=page_1, page_number=1, has_screenshot=True, predictions=[prediction]),
                    SimpleNamespace(id=page_2, page_number=2, has_screenshot=True, predictions=[prediction]),
                ],
            )
        ],
    )

    pages = to_extraction_out(run).documents[0].pages

    assert [pages[0].page_id, pages[1].page_id] == [page_1, page_2]
    assert [entity.pages for entity in (pages[0].entities[0], pages[1].entities[0])] == [[1, 2], [1, 2]]
    assert [(b.x_min, b.x_max) for b in pages[0].entities[0].boxes] == [(0.3, 0.5)]
    assert [(b.x_min, b.x_max) for b in pages[1].entities[0].boxes] == [(0.5, 0.7)]


def test_an_entity_that_could_not_be_located_has_no_boxes() -> None:
    page_id = uuid.uuid4()
    prediction = SimpleNamespace(
        id=uuid.uuid4(),
        kind=PredictionKind.ENTITY,
        name="nom",
        value="Dupont",
        confidence=None,
        source=PredictionSource.TEXTUAL,
        bounding_boxes=[],
    )
    run = SimpleNamespace(
        id=uuid.uuid4(),
        status=DossierStatus.TERMINE,
        execution_steps=[],
        expires_at=None,
        documents=[
            SimpleNamespace(
                name="a.pdf",
                pages=[SimpleNamespace(id=page_id, page_number=1, has_screenshot=False, predictions=[prediction])],
            )
        ],
    )

    assert to_extraction_out(run).documents[0].pages[0].entities[0].boxes == []
