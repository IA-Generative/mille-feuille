"""Ce que le consommateur reçoit dans le message `success` : un résumé borné du run.

Le run complet (texte de chaque page, boîtes, journaux d'étapes) pèse 20 à 50 Kio par page : il
est déposé tel quel sur le stockage d'async-api, à une clé déterministe sous le préfixe du client
(`resultat_file_id`), et le message ne porte que ce qu'un SI lit en premier — les catégories de
chaque page, les entités de chaque document, la sortie de chaque agent — sous une taille plafond.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — pydantic a besoin du type à l'exécution

from pydantic import BaseModel


class LabelResume(BaseModel):
    name: str
    confidence: float | None
    # `textual` (texte de la page) ou `visual` (apparence de la capture) : chaque page reçoit les deux.
    source: str


class PageResume(BaseModel):
    page_number: int
    labels: list[LabelResume]


class EntiteResume(BaseModel):
    name: str
    value: str
    confidence: float | None
    # `textual` (modèle de langage) ou `gliner` : la même valeur peut apparaître avec chaque source.
    source: str
    # Toutes les pages du document où l'entité a été trouvée.
    pages: list[int]


class DocumentResume(BaseModel):
    name: str
    page_count: int
    pages: list[PageResume]
    entities: list[EntiteResume]


class AgentResume(BaseModel):
    label: str
    status: str
    output: str | None
    # La sortie a été coupée à la borne du message ; la version complète est dans `resultat_file_id`.
    tronque: bool


class Durees(BaseModel):
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class MilleFeuilleResult(BaseModel):
    """Le contrat de sortie du service `mille-feuille`."""

    status: str
    run_id: str
    # Le run complet, en JSON, sur le stockage d'async-api : `{client_id}/{task_id}/resultat.json`.
    resultat_file_id: str
    resultat_octets: int
    documents: list[DocumentResume]
    agents: list[AgentResume]
    durees: Durees
    # Des entités ou des pages ont été retirées du résumé pour tenir sous la borne ; tout est dans le fichier.
    tronque: bool = False
