"""Tâche de suggestion d'analyse pour dossier « à ranger » (issue #54).

- ``suggest_dossier_analyse`` : récupère le résumé du dossier + la liste des
  analyses disponibles, appelle le LLM pour classer les analyses par
  pertinence, et dépose les suggestions via l'API interne.

Le dossier doit avoir un résumé généré (issue #52) pour que la suggestion
soit pertinente. Si le résumé n'existe pas, la tâche utilise le contenu
brut des documents comme fallback.
"""

import logging

from app import api_client, usage
from app.celery_app import celery_app
from app.llm import suggest_analyses

logger = logging.getLogger(__name__)

# Limite de caractères pour le résumé envoyé au LLM.
_MAX_SUMMARY_CHARS = 30_000


def _truncate(text: str, limit: int = _MAX_SUMMARY_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[... contenu tronqué ...]"


def _document_text(document: dict) -> str | None:
    """Retourne le texte représentant un document : résumé individuel si
    disponible, sinon le contenu brut des pages, sinon None."""
    doc_summary = (document.get("summary") or {}).get("content")
    if doc_summary:
        return f"### Document : {document['name']}\n{doc_summary}"

    pages = document.get("pages", [])
    if not pages:
        return None
    page_content = "\n".join(f"Page {p['page_number']}: {p.get('content') or '(vide)'}" for p in pages)
    return f"### Document : {document['name']}\n{page_content}"


def _build_dossier_content(dossier: dict) -> str:
    """Construit le contenu textuel représentant le dossier pour le LLM.
    Utilise le résumé global (issue #52) si disponible, sinon les résumés
    individuels des documents, sinon le contenu brut des pages. Inclut
    également les synthèses des agents (ExecutionStep.output)."""
    parts: list[str] = []

    # Résumé global du dossier (le plus récent)
    dossier_summary = (dossier.get("summary") or {}).get("content")
    if dossier_summary:
        parts.append(dossier_summary)
    else:
        # Fallback : résumés individuels ou contenu brut des documents
        for document in dossier["documents"]:
            doc_text = _document_text(document)
            if doc_text:
                parts.append(doc_text)

    # Synthèses des agents (ExecutionStep.output)
    for step in dossier.get("execution_steps", []):
        output = step.get("output")
        if output:
            parts.append(f"### {step['label']}\n{output}")

    return "\n\n".join(parts) if parts else ""


def _enrich_suggestions(suggestions: list, analyses_by_id: dict[str, dict]) -> list[dict]:
    """Enrichit les suggestions du LLM avec le nom de l'analyse pour
    l'affichage côté frontend. Filtre les suggestions référençant des
    analyses inconnues."""
    result: list[dict] = []
    for suggestion in suggestions:
        analyse = analyses_by_id.get(suggestion.analyse_id)
        if analyse is None:
            logger.warning("LLM suggested unknown analyse %s, skipping", suggestion.analyse_id)
            continue
        result.append(
            {
                "analyse_id": suggestion.analyse_id,
                "name": analyse["name"],
                "score": suggestion.score,
                "rationale": suggestion.rationale,
            }
        )
    return result


@celery_app.task(name="app.tasks.suggest_dossier_analyse", bind=True)
def suggest_dossier_analyse(self, dossier_id: str) -> None:
    """Génère des suggestions d'analyse pour un dossier « à ranger » :
    récupère le résumé du dossier (ou fallback sur le contenu brut), liste
    les analyses disponibles via l'API agent, appelle le LLM, et dépose les
    suggestions."""
    usage.bind("suggest_dossier_analyse", dossier_id=dossier_id)
    with api_client.get_client() as client:
        api_client.set_suggestion_status(client, dossier_id, status="en_cours")
        try:
            dossier = api_client.get_dossier(client, dossier_id)
            content = _truncate(_build_dossier_content(dossier))

            if not content:
                logger.warning("No content for suggestion on dossier %s", dossier_id)
                api_client.deposit_suggested_analyses(client, dossier_id, suggestions=[])
                return

            # Lister les analyses disponibles via l'API agent
            analyses_response = api_client.list_agent_analyses(client, page_size=100)
            analyses = analyses_response.get("items", [])
            if not analyses:
                logger.warning("No analyses available for suggestion on dossier %s", dossier_id)
                api_client.deposit_suggested_analyses(client, dossier_id, suggestions=[])
                return

            logger.info(
                "Suggesting analyses for dossier %s (%d chars, %d analyses)",
                dossier_id,
                len(content),
                len(analyses),
            )

            result = suggest_analyses(dossier_summary=content, analyses=analyses)
            analyses_by_id = {a["id"]: a for a in analyses}
            suggestions_out = _enrich_suggestions(result.suggestions, analyses_by_id)

            api_client.deposit_suggested_analyses(client, dossier_id, suggestions=suggestions_out)
            logger.info("Suggested %d analyses for dossier %s", len(suggestions_out), dossier_id)
        except Exception as error:
            logger.exception("Analyse suggestion failed for %s", dossier_id)
            api_client.set_suggestion_status(client, dossier_id, status="échec", error=str(error))
            raise
