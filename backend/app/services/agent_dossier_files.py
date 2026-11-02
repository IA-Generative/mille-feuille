"""L'ajout de fichiers à un dossier par l'assistant (serveur MCP) : les octets arrivent en base64 dans un corps JSON,
pas en multipart (pas d'`UploadFile` ici, même raison que `routers/ephemeral.py::_create_run`)."""

import base64
import uuid

from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_client import dispatch_text_extraction
from app.connectors import s3_connector
from app.core.dossier_guard import check_dossier_access
from app.core.security.factory import RequestContext
from app.repositories.dossier_repository import DossierRepository
from app.routers.dossiers import _get_or_404 as get_dossier_or_404


class AgentDossierFileIn(BaseModel):
    name: str
    content_base64: str
    mimetype: str = "application/octet-stream"


class AgentDossierFilesIn(BaseModel):
    files: list[AgentDossierFileIn]


async def add_agent_dossier_files(
    dossier_id: uuid.UUID, body: AgentDossierFilesIn, db: AsyncSession, person: RequestContext
):  # noqa: ANN201
    """Équivalent de POST /dossiers/{id}/documents, au nom de la personne : elle doit pouvoir écrire dans le dossier."""
    await check_dossier_access(db, dossier_id, person, method="POST", write=True)
    repository = DossierRepository(db)
    dossier = await get_dossier_or_404(repository, dossier_id, person)
    documents = []
    for f in body.files:
        data = base64.b64decode(f.content_base64)
        s3_key = f"dossiers/{dossier_id}/{uuid.uuid4()}-{f.name or 'document'}"
        await run_in_threadpool(s3_connector.upload, s3_key, data, f.mimetype)
        documents.append({"name": f.name or "document", "size": len(data), "s3_key": s3_key, "mimetype": f.mimetype})
    created = await repository.add_documents(dossier, documents)
    for document in created:
        dispatch_text_extraction(str(document.id))
    return await get_dossier_or_404(repository, dossier_id, person)
