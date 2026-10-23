from pydantic import BaseModel


class LlmModel(BaseModel):
    id: str


class LlmModelsResponse(BaseModel):
    models: list[LlmModel]


class LlmEmbeddingModel(BaseModel):
    id: str
    # Taille des vecteurs que le modèle produit.
    dimension: int


class LlmEmbeddingModelsResponse(BaseModel):
    models: list[LlmEmbeddingModel]


class LlmModelsCacheCleared(BaseModel):
    """Réponse de DELETE /api/models/cache : confirme que le cache Redis
    des modèles chat a bien été invalidé."""

    cleared: bool
