from pydantic import BaseModel, field_validator

from app.schemas.analyse import Version

MAX_QUESTION_CHARS = 300


class FrequentQuestions(BaseModel):
    """Les questions fréquentes d'une analyse : chaque dossier en reçoit la réponse une fois analysé."""

    questions: list[str] = []

    @field_validator("questions")
    @classmethod
    def _clean(cls, questions: list[str]) -> list[str]:
        """Le texte de chaque question, espaces en trop retirés ; les vides et les doublons (casse ignorée) sont
        écartés, l'ordre de la personne est gardé."""
        seen: set[str] = set()
        cleaned: list[str] = []
        for question in questions:
            text = " ".join(question.split())
            if not text:
                continue
            if len(text) > MAX_QUESTION_CHARS:
                raise ValueError(f"Une question ne dépasse pas {MAX_QUESTION_CHARS} caractères.")
            if text.casefold() in seen:
                continue
            seen.add(text.casefold())
            cleaned.append(text)
        return cleaned


class FrequentQuestionsOut(BaseModel):
    questions: list[str]
    versions: list[Version[FrequentQuestions]] = []
