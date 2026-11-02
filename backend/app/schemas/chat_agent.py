from pydantic import BaseModel


class ChatAgentOut(BaseModel):
    """Un agent de l'analyse que la personne peut interroger dans le chat du dossier."""

    name: str
    # Son rôle en une ligne : le début de son prompt.
    role: str
