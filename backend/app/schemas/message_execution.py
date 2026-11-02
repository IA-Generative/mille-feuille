"""Le détail de l'exécution d'une réponse de l'assistant : ce qu'il a fait pour la produire (plan, outils appelés avec
leurs arguments et leurs résultats, relances). Gardé avec le message, montré dans une modale à côté des pouces."""

from pydantic import BaseModel, Field

MAX_STEPS = 40
MAX_NOTES = 20
# Un résultat d'outil peut être un dossier entier : on en garde le début, de quoi comprendre ce que le modèle a lu.
MAX_RESULT_CHARS = 3000
MAX_ARGUMENTS_CHARS = 2000


class ExecutionStep(BaseModel):
    """Un appel d'outil : ses arguments, ce qu'il a rendu, combien de temps il a pris."""

    tool_name: str = Field(max_length=200)
    # L'agent de l'analyse qui l'a appelé, quand c'est un agent qui répond.
    agent: str | None = Field(default=None, max_length=200)
    arguments: dict = Field(default_factory=dict)
    result: str | None = Field(default=None, max_length=MAX_RESULT_CHARS + 20)
    # Millisecondes depuis le début de la réponse.
    at_ms: int = 0
    duration_ms: int | None = None


class MessageExecution(BaseModel):
    # Ce que le plan a décidé : direct, search, act, agent, clarify, assistant.
    mode: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=200)
    # Tours du modèle dans la boucle d'outils, quand il y en a eu une.
    iterations: int | None = None
    duration_ms: int | None = None
    # Ce qui s'est écarté du cas normal : appel d'outil repris, réponse redemandée, limite d'appels atteinte...
    notes: list[str] = Field(default_factory=list, max_length=MAX_NOTES)
    steps: list[ExecutionStep] = Field(default_factory=list, max_length=MAX_STEPS)
    # Appels au-delà de MAX_STEPS : comptés, pas gardés.
    omitted_steps: int = 0
