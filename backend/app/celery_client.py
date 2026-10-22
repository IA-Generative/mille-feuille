from celery import Celery, chain, group

from app.config import RedisSettings

_redis_settings = RedisSettings()

# Producteur seulement : le backend ne définit ni n'exécute de tâches, il se
# contente d'en déposer sur la même file Redis que celle où
# worker/document_process et worker/agent_execution écoutent (voir leurs
# celery_app.py - même nom de tâche, aucune queue dédiée des deux côtés).
# Le backend ne lit un résultat que pour l'extraction des champs d'un modèle (#138), avec un
# délai court ; les autres tâches sont lancées sans attendre.
celery_client = Celery("mille-feuille-backend", broker=_redis_settings.REDIS_URL, backend=_redis_settings.REDIS_URL)


# Files des workers dédiés (voir worker/agent_execution, CELERY_QUEUES) : la classification et l'extraction d'entités
# ne partagent plus la file agent_execution.
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
    """Enchaîne tout le pipeline d'un dossier : extraction de texte de tous les documents, puis (toutes les pages
    créées) classification et extraction d'entités en parallèle, puis (quand les deux sont finies) exécution des
    agents. Sans cet ordre, la classification et l'extraction liraient un dossier sans pages et concluraient sur
    « 0/0 ». Signatures immuables : le résultat d'une étape n'est jamais passé en argument à la suivante.
    Si une étape échoue, la suivante ne part pas."""

    def signature(name: str, args: list[str], queue: str | None = None):
        return celery_client.signature(name, args=args, queue=queue, immutable=True)

    return (
        chain(
            group(signature("app.tasks.extract_document_text", [document_id]) for document_id in document_ids),
            group(
                signature("app.tasks.classify_dossier", [dossier_id], CLASSIFICATION_QUEUE),
                signature("app.tasks.extract_dossier_entities", [dossier_id], ENTITY_EXTRACTION_QUEUE),
            ),
            signature("app.tasks.run_agents", [dossier_id], "agent_execution"),
        )
        .apply_async()
        .id
    )


def dispatch_agent_execution(dossier_id: str, acting_user: str | None = None) -> str:
    """Dépose la tâche d'exécution des agents sur la file agent_execution.
    Le worker attend que la classification et l'extraction soient terminées,
    puis exécute chaque agent via un graphe LangGraph avec des outils de
    recherche (BM25), lecture de pages, et consultation des prédictions.

    `acting_user` est la personne qui a lancé l'analyse : les agents appellent les serveurs MCP **en son nom**. Absente
    (exécution sans personne), ils n'ont accès qu'aux outils internes."""
    args = [dossier_id] if acting_user is None else [dossier_id, acting_user]
    return celery_client.send_task("app.tasks.run_agents", args=args, queue="agent_execution").id


def dispatch_chat_response(conversation_id: str, dossier_id: str) -> str:
    """Dépose la tâche de réponse au chat sur la file agent_execution.
    Le worker charge l'historique de la conversation + les synthèses
    existantes (ExecutionStep.output), construit un graphe LangGraph avec
    les outils de recherche, et dépose la réponse de l'assistant (avec
    sources) via l'API interne. Les événements intermédiaires (tool_calls,
    tool_results) sont streamés via la table chat_events."""
    return celery_client.send_task(
        "app.tasks.run_chat",
        args=[conversation_id, dossier_id],
        queue="agent_execution",
    ).id


def dispatch_note_proposals(note_id: str) -> str:
    """Dépose l'analyse d'une note sur la file agent_execution (issue #117) : le
    worker lit la note et l'analyse de dossier, demande au LLM les mises à jour
    que la note justifie, et dépose des **propositions en attente** (rien n'est
    appliqué). Le suivi est porté par la note (analysis_status)."""
    return celery_client.send_task("app.tasks.propose_from_note", args=[note_id], queue="agent_execution").id


def dispatch_document_generation(draft_id: str, names: list[str] | None = None, instruction: str | None = None) -> str:
    """Dépose la génération des valeurs d'un brouillon de document sur la file agent_execution (issue #141) :
    le worker lit le brouillon, la révision figée de l'analyse et les notes, demande au LLM une valeur par champ
    et dépose des **propositions** (une valeur validée n'est jamais réécrite). ``names`` limite les champs
    (régénération) ; ``instruction`` est la consigne facultative de l'instructeur. Le suivi est porté par le
    brouillon (generation_status)."""
    return celery_client.send_task(
        "app.tasks.generate_document_fields", args=[draft_id, names, instruction], queue="agent_execution"
    ).id


def dispatch_helper_chat_response(conversation_id: str, model: str | None = None) -> str:
    """Dépose la tâche de réponse de l'agent helper sur la file
    agent_execution (issue #50). Contrairement à dispatch_chat_response, pas
    de dossier_id : la conversation n'est pas rattachée à un dossier unique,
    le worker charge son historique via /internal/agent-conversations/{id}
    et construit son propre graphe (outils de recherche/création
    d'analyses et de dossiers, lancement du pipeline). Si ``model`` est
    fourni, il surcharge le modèle par défaut du worker."""
    return celery_client.send_task(
        "app.tasks.run_helper_chat",
        args=[conversation_id, model],
        queue="agent_execution",
    ).id


def dispatch_document_summary(dossier_id: str, document_id: str) -> str:
    """Dépose la tâche de génération de résumé d'un document sur la file
    agent_execution (issue #52). Le worker récupère les pages du document,
    concatène leur contenu, appelle le LLM pour produire un résumé concis,
    et dépose le résultat via l'API interne."""
    return celery_client.send_task(
        "app.tasks.run_document_summary",
        args=[dossier_id, document_id],
        queue="agent_execution",
    ).id


def dispatch_dossier_summary(dossier_id: str) -> str:
    """Dépose la tâche de génération du résumé global d'un dossier sur la
    file agent_execution (issue #52). Le worker récupère les résumés
    individuels des documents + les synthèses des agents, et produit une
    vue d'ensemble du dossier."""
    return celery_client.send_task(
        "app.tasks.run_dossier_summary",
        args=[dossier_id],
        queue="agent_execution",
    ).id


def dispatch_analyse_suggestion(dossier_id: str) -> str:
    """Dépose la tâche de génération des suggestions d'analyse pour un
    dossier « à ranger » sur la file agent_execution (issue #54). Le worker
    récupère les résumés du dossier + la liste des analyses disponibles,
    appelle le LLM pour classer les analyses par pertinence, et dépose les
    suggestions via l'API interne."""
    return celery_client.send_task(
        "app.tasks.suggest_dossier_analyse",
        args=[dossier_id],
        queue="agent_execution",
    ).id


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
