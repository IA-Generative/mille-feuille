import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas.question_answer import QuestionAnswerSourceOut


class PresentationClassificationOut(BaseModel):
    label: str
    # 0-100 ; absente quand la classification n'en donne pas.
    confidence: int | None = None


class PresentationEntityOut(BaseModel):
    name: str
    value: str
    # La page d'où vient la valeur.
    page: int | None = None


class PresentationAgentOut(BaseModel):
    name: str
    output: str


class PresentationDocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    label: str | None = None
    page_count: int


class SuggestedQuestionOut(BaseModel):
    """Une question dont la réponse est déjà prête : elle s'affiche sans attendre le modèle, avec ses sources."""

    id: uuid.UUID
    question: str
    answer: str
    sources: list[QuestionAnswerSourceOut] = []


class DossierPresentationOut(BaseModel):
    """Ce que la conversation montre en tête : l'essentiel du dossier, le détail à un clic.

    `status` : `pending` (l'analyse tourne), `ready`, `failed`, ou `idle` (pas encore lancée ou arrêtée : rien à
    montrer)."""

    status: Literal["idle", "pending", "ready", "failed"]
    # Le résumé ou les réponses prêtes se calculent encore : la page recharge la présentation jusqu'à ce que tout
    # y soit.
    refreshing: bool = False
    error: str | None = None
    dossier_name: str
    summary: str | None = None
    # Le résumé n'a pas pu être généré : la raison, pour proposer de réessayer.
    summary_error: str | None = None
    classification: PresentationClassificationOut | None = None
    entities: list[PresentationEntityOut] = []
    agents: list[PresentationAgentOut] = []
    documents: list[PresentationDocumentOut] = []
    suggestions: list[SuggestedQuestionOut] = []
