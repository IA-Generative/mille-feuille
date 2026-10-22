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


class ToolTestIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000, description="La demande, en langage naturel.")
    # Identifiant de modèle tel que renvoyé par GET /models ; None = le premier modèle de chat du hub.
    model: str | None = None
    # Obligatoire pour un tool qui modifie des données : le test l'exécute pour de vrai.
    confirmed: bool = False


class ToolTestCallOut(BaseModel):
    name: str
    arguments: dict[str, Any]


class ToolTestOut(ToolCallOut):
    """Le résultat d'un test : la sortie brute du tool, et l'appel que le modèle a fait pour l'obtenir."""

    model: str | None = None
    call: ToolTestCallOut | None = None
