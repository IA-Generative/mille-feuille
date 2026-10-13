"""Tâche de classification documentaire.

Pour chaque page de chaque document du dossier :
1. Télécharger la capture de la page depuis S3 (screenshot_key).
2. Demander au VLM de décrire l'image (description textuelle).
3. Combiner la description VLM + le texte OCR de la page.
4. Demander au LLM de classifier la page (structured output) parmi les
   labels définis dans l'analyse.
5. Déposer la prédiction (kind=LABEL) via l'API interne.

Par défaut la classification est mono-label : une seule prédiction LABEL par
page. Si l'analyse est multi-label, une prédiction LABEL par label retenu.
Chacune pointe vers le label_definition_id correspondant.
"""

import logging

from app import api_client, llm
from app.celery_app import celery_app
from app.fingerprint import classification_fingerprint
from app.storage import storage

logger = logging.getLogger(__name__)

_STATUS_TERMINE = "terminé"
_STATUS_ECHEC = "échec"


def _find_step_id(dossier: dict, kind: str) -> str | None:
    for step in dossier.get("execution_steps", []):
        if step["kind"] == kind:
            return step["id"]
    return None


def _describe_page_image(page: dict) -> str:
    """Télécharge la capture de la page depuis S3 et demande au VLM de la
    décrire. Renvoie une chaîne vide si la capture est indisponible ou si
    la description échoue."""
    screenshot_key = page.get("screenshot_key")
    if not screenshot_key:
        return ""
    try:
        image_bytes = storage.get_object(screenshot_key)
        return llm.describe_page_image(image_bytes)
    except Exception:
        logger.warning(
            "Failed to describe image for page %s, falling back to text only",
            page["id"],
            exc_info=True,
        )
        return ""


def _classify_page(
    client,
    page: dict,
    label_defs: list[dict],
    label_by_name: dict,
    classification_prompt: str,
    unit_id: str | None = None,
    multi_label: bool = False,
) -> bool:
    """Classifie une page et dépose la prédiction. Renvoie True si la
    classification a réussi."""
    page_text = page.get("content") or ""
    image_description = _describe_page_image(page)

    result = llm.classify_page(
        page_text=page_text,
        image_description=image_description,
        label_definitions=label_defs,
        classification_prompt=classification_prompt,
        multi_label=multi_label,
    )

    predictions = result.predictions if multi_label else [result.prediction]
    seen: set[str] = set()
    for prediction in predictions:
        if prediction.label_name in seen:
            continue
        seen.add(prediction.label_name)
        label_def = label_by_name.get(prediction.label_name)
        label_definition_id = label_def["id"] if label_def else None

        api_client.add_prediction(
            client,
            page["id"],
            kind="label",
            name=prediction.label_name,
            value=prediction.label_name,
            confidence=prediction.confidence,
            label_definition_id=label_definition_id,
            unit_id=unit_id,
        )
        logger.info(
            "Page %s classified as '%s' (confidence=%.2f)",
            page["id"],
            prediction.label_name,
            prediction.confidence,
        )
    return True


@celery_app.task(name="app.tasks.classify_dossier", bind=True)
def classify_dossier(self, dossier_id: str) -> None:
    with api_client.get_client() as client:
        dossier = api_client.get_dossier(client, dossier_id)
        analyse_id = dossier["analyse_id"]

        step_id = _find_step_id(dossier, "classification")
        if step_id:
            api_client.add_execution_log(client, step_id, message="Classification démarrée")

        try:
            definitions = api_client.get_analyse_definitions(client, analyse_id)
            label_defs = definitions["classification"]["labels"]
            classification_prompt = definitions["classification"]["prompt"]
            multi_label = definitions["classification"].get("multi_label", False)

            if not label_defs:
                logger.warning(
                    "No label definitions for analyse %s, skipping classification",
                    analyse_id,
                )
                if step_id:
                    api_client.complete_execution_step(
                        client,
                        step_id,
                        status=_STATUS_TERMINE,
                        output="Aucun label défini",
                    )
                return

            label_by_name = {label["name"]: label for label in label_defs}
            total_pages = 0
            classified_pages = 0
            reused_pages = 0

            for document in dossier["documents"]:
                for page in document["pages"]:
                    total_pages += 1
                    # Une unité de calcul par page dans l'analyse de dossier.
                    unit = api_client.declare_unit(
                        client,
                        dossier_id,
                        "classification",
                        {"document_id": document["id"], "page_id": page["id"], "page_number": page["page_number"]},
                        fingerprint=classification_fingerprint(page, label_defs, classification_prompt, multi_label),
                    )
                    if unit is not None and unit.reused:
                        # Relance incrémentale (#119) : entrées inchangées, résultat
                        # déjà repris de l'analyse précédente, ni VLM ni LLM.
                        classified_pages += 1
                        reused_pages += 1
                        continue
                    unit_id = unit.id if unit else None
                    try:
                        if _classify_page(
                            client, page, label_defs, label_by_name, classification_prompt, unit_id, multi_label
                        ):
                            classified_pages += 1
                    except Exception:
                        api_client.complete_unit(client, unit_id, _STATUS_ECHEC)
                        raise
                    api_client.complete_unit(client, unit_id, _STATUS_TERMINE)

            output = f"{classified_pages}/{total_pages} page(s) classifiée(s)"
            if reused_pages:
                output += f" (dont {reused_pages} reprise(s) de l'exécution précédente)"
            if step_id:
                api_client.complete_execution_step(client, step_id, status=_STATUS_TERMINE, output=output)
            logger.info("Classification complete for dossier %s: %s", dossier_id, output)

        except Exception as error:
            logger.exception("Classification failed for dossier %s", dossier_id)
            if step_id:
                api_client.add_execution_log(client, step_id, level="error", message=str(error))
                api_client.complete_execution_step(client, step_id, status=_STATUS_ECHEC, output=str(error))
            raise
