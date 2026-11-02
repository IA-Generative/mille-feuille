"""Suggestion d'analyse pour un dossier « à ranger » (issue #54).

Le résumé du dossier (issue #52) et la liste des analyses disponibles sont donnés au LLM, qui classe les analyses par
pertinence ; les suggestions sont déposées sur le dossier. Sans résumé, le contenu brut des documents sert de repli."""

import logging
import uuid

from app.agent import usage
from app.agent.documents import load_dossier
from app.agent.llm import suggest_analyses
from app.db import async_session_factory
from app.models.dossier import SuggestionStatus
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_repository import DossierRepository

logger = logging.getLogger(__name__)

# Limite de caractères pour le résumé envoyé au LLM.
_MAX_SUMMARY_CHARS = 30_000


def _truncate(text: str, limit: int = _MAX_SUMMARY_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[... contenu tronqué ...]"


def _document_text(document: dict) -> str | None:
    """Le texte d'un document : son résumé s'il en a un, sinon le contenu brut des pages, sinon None."""
    doc_summary = (document.get("summary") or {}).get("content")
    if doc_summary:
        return f"### Document : {document['name']}\n{doc_summary}"

    pages = document.get("pages", [])
    if not pages:
        return None
    page_content = "\n".join(f"Page {p['page_number']}: {p.get('content') or '(vide)'}" for p in pages)
    return f"### Document : {document['name']}\n{page_content}"


def _build_dossier_content(dossier: dict) -> str:
    """Le dossier pour le LLM : résumé global si disponible, sinon les documents ; plus les synthèses des agents."""
    parts: list[str] = []
    dossier_summary = (dossier.get("summary") or {}).get("content")
    if dossier_summary:
        parts.append(dossier_summary)
    else:
        for document in dossier["documents"]:
            doc_text = _document_text(document)
            if doc_text:
                parts.append(doc_text)

    for step in dossier.get("execution_steps", []):
        if step.get("output"):
            parts.append(f"### {step['label']}\n{step['output']}")

    return "\n\n".join(parts)


def _enrich_suggestions(suggestions: list, analyses_by_id: dict[str, dict]) -> list[dict]:
    """Ajoute le nom de l'analyse pour l'affichage ; écarte les suggestions d'analyses inconnues."""
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


async def suggest_dossier_analyse(dossier_id: str) -> None:
    usage.bind("suggest_dossier_analyse", dossier_id=dossier_id)
    async with async_session_factory() as db:
        repository = DossierRepository(db)
        dossier_row = await repository.get(uuid.UUID(dossier_id))
        if dossier_row is None:
            logger.warning("Dossier %s introuvable, suggestion ignorée", dossier_id)
            return
        await repository.set_suggestion_status(dossier_row, SuggestionStatus.EN_COURS)
        try:
            dossier = await load_dossier(db, dossier_id)
            content = _truncate(_build_dossier_content(dossier))
            if not content:
                logger.warning("No content for suggestion on dossier %s", dossier_id)
                await repository.set_suggested_analyses(dossier_row, [])
                return

            rows, _total = await AnalyseRepository(db).list_paginated(page=1, page_size=100, q=None)
            analyses = [{"id": str(a.id), "name": a.name, "description": a.description} for a in rows]
            if not analyses:
                logger.warning("No analyses available for suggestion on dossier %s", dossier_id)
                await repository.set_suggested_analyses(dossier_row, [])
                return

            logger.info(
                "Suggesting analyses for dossier %s (%d chars, %d analyses)", dossier_id, len(content), len(analyses)
            )
            result = await suggest_analyses(dossier_summary=content, analyses=analyses)
            suggestions = _enrich_suggestions(result.suggestions, {a["id"]: a for a in analyses})
            await repository.set_suggested_analyses(dossier_row, suggestions)
            logger.info("Suggested %d analyses for dossier %s", len(suggestions), dossier_id)
        except Exception as error:
            logger.exception("Analyse suggestion failed for %s", dossier_id)
            await db.rollback()
            await repository.set_suggestion_status(dossier_row, SuggestionStatus.ECHEC, str(error))
