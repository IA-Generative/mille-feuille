from loguru import logger

from app.celery_app import celery_app
from app.config import settings
from app.contracts import RegionToDescribe
from app.hub import get_hub_describer
from app.storage import storage


@celery_app.task(name="app.tasks.describe_regions")
def describe_regions(
    document_id: str,
    page_number: int,
    image_key: str,
    regions: list[dict],
    prompt: str | None = None,
    model: str | None = None,
) -> dict:
    """Une description de chaque région (`{"id", "box", "kind"}`, boîte entre 0 et 1 sur la page) de l'image de page
    à `image_key`, en PageDescriptions JSON : par id de région, avec le modèle et ce que ça a coûté.

    `model` est un modèle du hub qui lit les images (par défaut `VLM_MODEL`) ; `prompt` remplace la question posée
    (sinon une question pour une image, une pour un tableau)."""
    to_describe = [RegionToDescribe.model_validate(region) for region in regions]
    page = storage.get_object(image_key)
    result = get_hub_describer().describe(
        page, to_describe, document_id, page_number, model or settings.VLM_MODEL, prompt
    )
    logger.info(
        f"Page {page_number} of {document_id}: {len(result.descriptions)} of {len(to_describe)} region(s) described "
        f"by {result.model_version} in {result.usage.seconds:.1f} s"
    )
    return result.model_dump(mode="json")
