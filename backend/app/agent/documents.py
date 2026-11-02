"""Vues du dossier pour l'agent : le dossier tel que le worker le lisait (`InternalDossierOut`), en dict."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dossier_repository import DossierRepository
from app.schemas.dossier import InternalDossierOut


class DossierNotFoundError(Exception):
    pass


async def load_dossier(db: AsyncSession, dossier_id: uuid.UUID | str) -> dict:
    """Le dossier avec ses documents, pages, résumés et étapes d'exécution, à jour de la base."""
    dossier = await DossierRepository(db).get(uuid.UUID(str(dossier_id)))
    if dossier is None:
        raise DossierNotFoundError(f"Dossier {dossier_id} introuvable")
    return InternalDossierOut.model_validate(dossier).model_dump(mode="json")


def document_label(document: dict) -> str:
    """Nom du document, suivi de sa source s'il en a une (« passeport.pdf — source : Guichet »)."""
    name = document.get("name", "")
    source = (document.get("source") or {}).get("name")
    return f"{name} — source : {source}" if source else name
