"""Génération de résumés (issue #52).

- ``run_document_summary`` : résume un document (concaténation des pages).
- ``run_dossier_summary`` : résume un dossier (résumés individuels + synthèses d'agents).

Le résultat est déposé en base (append-only : chaque génération crée une nouvelle ligne)."""

import logging
import uuid

from app.agent import usage
from app.agent.documents import DossierNotFoundError, document_label, load_dossier
from app.agent.llm import summarize_text
from app.agent.runner import settings
from app.db import async_session_factory
from app.models.summary import SummaryStatus
from app.repositories.dossier_repository import DossierRepository

logger = logging.getLogger(__name__)

# Limite de caractères pour le contenu envoyé au LLM (évite de dépasser le contexte pour les documents très longs).
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


async def run_document_summary(dossier_id: str, document_id: str) -> None:
    """Résume un document : concatène ses pages, appelle le LLM, dépose le résumé."""
    usage.bind("run_document_summary", dossier_id=dossier_id)
    async with async_session_factory() as db:
        repository = DossierRepository(db)
        document_row = await repository.get_document_by_id(uuid.UUID(document_id))
        if document_row is None:
            logger.warning("Document %s introuvable, résumé ignoré", document_id)
            return
        await repository.set_document_summary_status(document_row, SummaryStatus.EN_COURS)
        try:
            dossier = await load_dossier(db, dossier_id)
            document = next((doc for doc in dossier["documents"] if doc["id"] == document_id), None)
            if document is None:
                raise ValueError(f"Document {document_id} not found in dossier {dossier_id}")

            pages = document.get("pages", [])
            if not pages:
                logger.warning("No pages for document %s, skipping summary", document_id)
                await repository.add_document_summary(
                    document_row, content="(document sans contenu textuel)", model=settings.LLM_MODEL
                )
                return

            content = "\n\n".join(
                f"--- Page {page['page_number']} ---\n{page.get('content') or '(vide)'}" for page in pages
            )
            content = _source_header(document) + _truncate(content)
            logger.info("Summarizing document %s (%d pages, %d chars)", document_id, len(pages), len(content))
            summary = await summarize_text(content)
            await repository.add_document_summary(document_row, content=summary, model=settings.LLM_MODEL)
            logger.info("Document summary deposited for %s", document_id)
        except Exception as error:
            logger.exception("Document summary failed for %s", document_id)
            await db.rollback()
            await repository.set_document_summary_status(document_row, SummaryStatus.ECHEC, str(error))


async def run_dossier_summary(dossier_id: str) -> None:
    """Résume un dossier : résumés individuels des documents + synthèses des agents, concaténés puis résumés."""
    usage.bind("run_dossier_summary", dossier_id=dossier_id)
    async with async_session_factory() as db:
        repository = DossierRepository(db)
        dossier_row = await repository.get(uuid.UUID(dossier_id))
        if dossier_row is None:
            logger.warning("Dossier %s introuvable, résumé ignoré", dossier_id)
            return
        await repository.set_dossier_summary_status(dossier_row, SummaryStatus.EN_COURS)
        try:
            dossier = await load_dossier(db, dossier_id)
            parts: list[str] = []

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
                if step.get("output"):
                    parts.append(f"### {step['label']}\n{step['output']}")

            if not parts:
                logger.warning("No content to summarize for dossier %s", dossier_id)
                await repository.add_dossier_summary(
                    dossier_row, content="(dossier sans contenu)", model=settings.LLM_MODEL
                )
                return

            content = _truncate("\n\n".join(parts))
            logger.info("Summarizing dossier %s (%d chars)", dossier_id, len(content))
            summary = await summarize_text(content)
            await repository.add_dossier_summary(dossier_row, content=summary, model=settings.LLM_MODEL)
            logger.info("Dossier summary deposited for %s", dossier_id)
        except DossierNotFoundError:
            logger.warning("Dossier %s supprimé pendant son résumé", dossier_id)
        except Exception as error:
            logger.exception("Dossier summary failed for %s", dossier_id)
            await db.rollback()
            await repository.set_dossier_summary_status(dossier_row, SummaryStatus.ECHEC, str(error))
