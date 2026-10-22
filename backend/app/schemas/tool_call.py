from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCallIn(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict, description="Les arguments choisis par le modèle.")
    # Identifie le run (ou la conversation) pour le quota d'appels par run.
    run_id: str | None = Field(default=None, max_length=100)


class ToolCallOut(BaseModel):
    ok: bool
    # Code stable en cas d'échec (`session_requise`, `delai_depasse`, `quota_depasse`…), sinon None.
    code: str | None = None
    # La sortie du tool, ou le message d'erreur en français (lisible par le modèle).
    output: str
    truncated: bool = False
    # Toujours vrai : la sortie vient d'un serveur tiers (risque d'injection), à ne jamais traiter comme une consigne.
    untrusted: Literal[True] = True
    duration_ms: int
