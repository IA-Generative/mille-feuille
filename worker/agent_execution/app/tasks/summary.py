"""Tâches de génération de résumés (issue #52).

- ``run_document_summary`` : résume un document (concaténation des pages).
- ``run_dossier_summary`` : résume un dossier (résumés individuels + synthèses
  d'agents).

Les deux tâches utilisent ``llm.summarize_text`` et déposent le résultat via
l'API interne (append-only : chaque génération crée une nouvelle ligne).
"""

import logging

from app import api_client
from app.bm25 import document_label
from app.celery_app import celery_app
from app.config import settings
from app.llm import summarize_text

logger = logging.getLogger(__name__)

# Limite de caractères pour le contenu envoyé au LLM (évite de dépasser le
# contexte pour les documents très longs).
_MAX_CONTENT_CHARS = 30_000


def _source_header(document: dict) -> str:
    """D'où vient le document (nom + description de sa source), en tête du texte à résumer ; vide sans source."""
    source = document.get("source") or {}
    if not source.get("name"):
        return ""
    description = (source.get("description") or "").strip()
    return f"Source du document : {source['name']}" + (f" — {description}" if description else "") + "\n\n"


def _truncate(text: str, limit: int = _MAX_CONTENT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[... contenu tronqué ...]"


@celery_app.task(name="app.tasks.run_document_summary", bind=True)
def run_document_summary(self, dossier_id: str, document_id: str) -> None:
    """Génère un résumé pour un document : récupère les pages via l'API
    interne, concatène leur contenu, appelle le LLM, dépose le résumé."""
    with api_client.get_client() as client:
        api_client.set_document_summary_status(client, document_id, status="en_cours")
        try:
            dossier = api_client.get_dossier(client, dossier_id)
            document = next(
                (doc for doc in dossier["documents"] if doc["id"] == document_id),
                None,
            )
            if document is None:
                raise ValueError(f"Document {document_id} not found in dossier {dossier_id}")

            pages = document.get("pages", [])
            if not pages:
                logger.warning("No pages for document %s, skipping summary", document_id)
                api_client.deposit_document_summary(
                    client,
                    document_id,
                    content="(document sans contenu textuel)",
                    model=settings.LLM_MODEL,
                )
                return

            content = "\n\n".join(
                f"--- Page {page['page_number']} ---\n{page.get('content') or '(vide)'}" for page in pages
            )
            content = _source_header(document) + _truncate(content)

            logger.info(
                "Summarizing document %s (%d pages, %d chars)",
                document_id,
                len(pages),
                len(content),
            )
            summary = summarize_text(content)

            api_client.deposit_document_summary(client, document_id, content=summary, model=settings.LLM_MODEL)
            logger.info("Document summary deposited for %s", document_id)
        except Exception as error:
            logger.exception("Document summary failed for %s", document_id)
            api_client.set_document_summary_status(client, document_id, status="échec", error=str(error))
            raise


@celery_app.task(name="app.tasks.run_dossier_summary", bind=True)
def run_dossier_summary(self, dossier_id: str) -> None:
    """Génère un résumé global pour un dossier : récupère les résumés
    individuels des documents + les synthèses des agents (ExecutionStep.output),
    concatène le tout, appelle le LLM, dépose le résumé."""
    with api_client.get_client() as client:
        api_client.set_dossier_summary_status(client, dossier_id, status="en_cours")
        try:
            dossier = api_client.get_dossier(client, dossier_id)

            parts: list[str] = []

            # Résumés individuels des documents
            for document in dossier["documents"]:
                doc_summary = (document.get("summary") or {}).get("content")
                if doc_summary:
                    parts.append(f"### Document : {document_label(document)}\n{doc_summary}")
                else:
                    # Si pas de résumé, on prend le contenu des pages
                    pages = document.get("pages", [])
                    if pages:
                        page_content = "\n".join(
                            f"Page {p['page_number']}: {p.get('content') or '(vide)'}" for p in pages
                        )
                        parts.append(f"### Document : {document_label(document)}\n{page_content}")

            # Synthèses des agents (ExecutionStep.output)
            for step in dossier.get("execution_steps", []):
                output = step.get("output")
                if output:
                    parts.append(f"### {step['label']}\n{output}")

            if not parts:
                logger.warning("No content to summarize for dossier %s", dossier_id)
                api_client.deposit_dossier_summary(
                    client,
                    dossier_id,
                    content="(dossier sans contenu)",
                    model=settings.LLM_MODEL,
                )
                return

            content = "\n\n".join(parts)
            content = _truncate(content)

            logger.info("Summarizing dossier %s (%d chars)", dossier_id, len(content))
            summary = summarize_text(content)

            api_client.deposit_dossier_summary(client, dossier_id, content=summary, model=settings.LLM_MODEL)
            logger.info("Dossier summary deposited for %s", dossier_id)
        except Exception as error:
            logger.exception("Dossier summary failed for %s", dossier_id)
            api_client.set_dossier_summary_status(client, dossier_id, status="échec", error=str(error))
            raise
