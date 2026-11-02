from celery import Celery, chain, group

from app.config import RedisSettings

_redis_settings = RedisSettings()

# Producteur seulement : le backend ne définit ni n'exécute de tâches, il se
# contente d'en déposer sur la même file Redis que celle où
# les workers (document_process, classification, extraction, rendu) écoutent
# (voir leurs celery_app.py - même nom de tâche).
# Le backend ne lit un résultat que pour l'extraction des champs d'un modèle (#138), avec un
# délai court ; les autres tâches sont lancées sans attendre.
celery_client = Celery("mille-feuille-backend", broker=_redis_settings.REDIS_URL, backend=_redis_settings.REDIS_URL)


# Files des workers dédiés : la classification et l'extraction d'entités ont chacune leur file.
CLASSIFICATION_QUEUE = "classification"
ENTITY_EXTRACTION_QUEUE = "entity_extraction"


def dispatch_text_extraction(document_id: str) -> str:
    return celery_client.send_task("app.tasks.extract_document_text", args=[document_id]).id


def dispatch_classification(dossier_id: str) -> str:
    """Dépose la tâche de classification documentaire sur la file
    classification. Le worker télécharge les captures de pages depuis S3,
    les décrit via un VLM, puis classifie chaque page via un LLM en
    structured output."""
    return celery_client.send_task("app.tasks.classify_dossier", args=[dossier_id], queue=CLASSIFICATION_QUEUE).id


def dispatch_entity_extraction(dossier_id: str) -> str:
    """Dépose la tâche d'extraction d'entités sur la file entity_extraction.
    Le worker regroupe les pages par batch et extrait les entités via un
    LLM en structured output."""
    return celery_client.send_task(
        "app.tasks.extract_dossier_entities", args=[dossier_id], queue=ENTITY_EXTRACTION_QUEUE
    ).id


def dispatch_dossier_pipeline(document_ids: list[str], dossier_id: str) -> str:
    """Enchaîne le pipeline d'un dossier : extraction de texte de tous les documents, puis (toutes les pages
    créées) classification et extraction d'entités en parallèle. Les agents, eux, sont lancés par le backend
    (voir app.agent.dispatch) et attendent la fin de ces deux étapes. Sans cet ordre, la classification et
    l'extraction liraient un dossier sans pages et concluraient sur « 0/0 ». Signatures immuables : le
    résultat d'une étape n'est jamais passé en argument à la suivante. Si une étape échoue, la suivante ne part pas."""

    def signature(name: str, args: list[str], queue: str | None = None):
        return celery_client.signature(name, args=args, queue=queue, immutable=True)

    return (
        chain(
            group(signature("app.tasks.extract_document_text", [document_id]) for document_id in document_ids),
            group(
                signature("app.tasks.classify_dossier", [dossier_id], CLASSIFICATION_QUEUE),
                signature("app.tasks.extract_dossier_entities", [dossier_id], ENTITY_EXTRACTION_QUEUE),
            ),
        )
        .apply_async()
        .id
    )


class TemplateExtractionError(Exception):
    """Le worker n'a pas pu lire le modèle (fichier invalide) : le message est destiné à l'administrateur."""


class RenderWorkerUnavailableError(Exception):
    """Le worker de rendu n'a pas répondu dans le délai."""


def inspect_template(template_key: str, timeout: int = 30) -> dict:
    """Demande au worker ``document_render`` de contrôler un modèle ODT déposé dans S3 (issues #138, #148) :
    ses champs, les polices qu'il utilise et les avertissements à l'import (polices absentes de l'image, champs
    natifs LibreOffice, images). Bloquant : à appeler hors de la boucle d'événements."""
    from celery.exceptions import TimeoutError as CeleryTimeoutError

    result = celery_client.send_task("app.tasks.inspect_template", args=[template_key], queue="document_render")
    try:
        return dict(result.get(timeout=timeout))
    except CeleryTimeoutError as error:
        raise RenderWorkerUnavailableError() from error
    except Exception as error:  # noqa: BLE001 - l'exception du worker revient sous un type générique
        raise TemplateExtractionError(str(error)) from error


class RenderFailedError(Exception):
    """Le worker de rendu a échoué (modèle illisible, LibreOffice en erreur) : message pour l'administrateur."""


def render_document(template_key: str, values: dict, output_prefix: str, timeout: int = 180) -> dict[str, str]:
    """Demande au worker ``document_render`` de remplir le modèle (déposé dans S3) et de déposer l'ODT et le PDF
    sous ``output_prefix`` (issue #143). Renvoie ``{"odt_key", "pdf_key"}``. Bloquant : à appeler hors de la
    boucle d'événements. Aucun LLM : l'assemblage est déterministe."""
    from celery.exceptions import TimeoutError as CeleryTimeoutError

    result = celery_client.send_task(
        "app.tasks.render_document", args=[template_key, values, output_prefix, True], queue="document_render"
    )
    try:
        return dict(result.get(timeout=timeout))
    except CeleryTimeoutError as error:
        raise RenderWorkerUnavailableError() from error
    except Exception as error:  # noqa: BLE001 - l'exception du worker revient sous un type générique
        raise RenderFailedError(str(error)) from error


def render_preview(template_key: str, values: dict, output_key: str, timeout: int = 120) -> str:
    """Demande au worker ``document_render`` un aperçu PDF du modèle rempli (issue #142), déposé sous
    ``output_key``. Seul le PDF est produit : rien d'autre n'est conservé. Bloquant : hors de la boucle d'événements."""
    from celery.exceptions import TimeoutError as CeleryTimeoutError

    result = celery_client.send_task(
        "app.tasks.render_preview", args=[template_key, values, output_key], queue="document_render"
    )
    try:
        return str(result.get(timeout=timeout))
    except CeleryTimeoutError as error:
        raise RenderWorkerUnavailableError() from error
    except Exception as error:  # noqa: BLE001 - l'exception du worker revient sous un type générique
        raise RenderFailedError(str(error)) from error
