import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class QuestionAnswerSourceOut(BaseModel):
    """Un passage cité par une réponse : le document, ses pages et l'extrait, avec le numéro cité dans le texte."""

    number: int | None = None
    dossier_document_id: str | None = None
    page_ids: list[str] = []
    excerpt: str | None = None


class QuestionAnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question: str
    answer: str
    sources: list[QuestionAnswerSourceOut] = []


class QuestionAnswersOut(BaseModel):
    """Les réponses prêtes d'un dossier. `status` : `pending` quand un calcul est en cours, `failed` quand une réponse a
    échoué (relançable), sinon `ready`. Seules les questions dont le dossier contient la réponse sont listées."""

    status: Literal["pending", "failed", "ready"]
    answers: list[QuestionAnswerOut] = []
