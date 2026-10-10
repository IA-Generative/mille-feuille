import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.chat_event import ChatEventKind
from app.models.conversation import MessageRole
from app.models.document_page import PredictionKind, PredictionValidationStatus
from app.models.dossier import (
    DossierStatus,
    ExecutionStepKind,
    ExecutionStepStatus,
    SuggestionStatus,
    TextExtractionStatus,
)
from app.models.execution_log import ExecutionLogLevel
from app.models.feedback import FeedbackReasonCode, FeedbackValue
from app.models.summary import SummaryStatus
from app.schemas.analyse import StatusDefinitionOut


class BoundingBoxIn(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class BoundingBoxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Page portant la zone : une source de message référence des bbox sans
    # connaître leur page, le frontend en a besoin pour les surligner.
    document_page_id: uuid.UUID
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class DocumentPageSummaryOut(BaseModel):
    """Référence légère à une page, utilisée dans les schémas qui pointent
    vers un ensemble de pages (prédiction, source de message) - la page
    complète (avec ses prédictions) est déjà accessible via DossierOut."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_number: int


class PredictionValidationIn(BaseModel):
    status: PredictionValidationStatus
    corrected_value: str | None = None
    bounding_box: BoundingBoxIn | None = None


class PredictionValidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    validator_user_id: str
    status: PredictionValidationStatus
    corrected_value: str | None
    bounding_box: BoundingBoxOut | None
    created_at: datetime


class DocumentPredictionSummaryOut(BaseModel):
    """Vue nichée dans DocumentPageOut.predictions : pas de `pages` ici (on
    est déjà sous une page) - la liste complète des pages d'une entité qui
    s'étend sur plusieurs d'entre elles n'est disponible que sur la
    prédiction elle-même (DocumentPredictionOut, endpoints dédiés)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: PredictionKind
    name: str
    value: str
    confidence: float | None
    # Présent seulement si la définition existe encore (voir le commentaire
    # sur DocumentPrediction.label_definition_id/entity_definition_id).
    label_definition_id: uuid.UUID | None
    entity_definition_id: uuid.UUID | None
    # Une classification n'a qu'un élément ; une entité peut n'être
    # localisée que par plusieurs zones, potentiellement sur d'autres pages.
    bounding_boxes: list[BoundingBoxOut]
    validations: list[PredictionValidationOut]


class DocumentPredictionOut(DocumentPredictionSummaryOut):
    # Une classification n'a qu'un élément ; une entité peut s'étendre sur
    # plusieurs pages.
    pages: list[DocumentPageSummaryOut]


class DossierResultRowOut(BaseModel):
    """Une ligne du détail des résultats d'un dossier (modale des cartes
    Classification / Entités) : la prédiction, le fichier et les pages qu'elle
    couvre."""

    id: uuid.UUID
    name: str
    value: str
    confidence: float | None
    document_id: uuid.UUID
    document_name: str
    # Pages du fichier couvertes par la prédiction et zones qui les surlignent : de quoi ouvrir la page source.
    pages: list[DocumentPageSummaryOut]
    bounding_boxes: list[BoundingBoxOut]


class DossierResultsBreakdownRowOut(BaseModel):
    """Répartition des résultats d'un dossier pour un fichier."""

    document_id: uuid.UUID
    document_name: str
    page_count: int
    classified_page_count: int
    entity_count: int


class DocumentPageIn(BaseModel):
    page_number: int
    width: int | None = None
    height: int | None = None
    content: str | None = None
    # Clé S3 de la capture de la page, déjà uploadée par le worker (voir
    # storage.put_object) au moment de cet appel - jamais renvoyée telle
    # quelle par l'API, uniquement via GET .../pages/{id}/screenshot.
    screenshot_key: str | None = None


class DocumentPredictionIn(BaseModel):
    kind: PredictionKind
    name: str
    value: str
    confidence: float | None = None
    label_definition_id: uuid.UUID | None = None
    entity_definition_id: uuid.UUID | None = None
    # Pages/bbox additionnelles au-delà de la page de l'URL (POST
    # .../pages/{page_id}/predictions) : toujours incluse dans le résultat,
    # inutile de la répéter ici. Les bbox doivent déjà exister (voir POST
    # .../pages/{page_id}/bounding-boxes).
    page_ids: list[uuid.UUID] = []
    bounding_box_ids: list[uuid.UUID] = []
    # Unité de calcul de l'analyse de dossier qui produit cette prédiction
    # (voir POST /internal/dossiers/{id}/analysis-units). Facultatif : sans
    # elle, la prédiction est déposée comme avant, sans élément d'analyse.
    unit_id: uuid.UUID | None = None


class MessageSourceIn(BaseModel):
    dossier_document_id: uuid.UUID | None = None
    execution_step_id: uuid.UUID | None = None
    excerpt: str | None = None
    # Du plus large au plus précis : le document ci-dessus suffit à minima,
    # mais la réponse peut citer un ensemble de pages ou, plus précisément,
    # un ensemble de bbox (déjà créées) sur ces pages.
    page_ids: list[uuid.UUID] = []
    bounding_box_ids: list[uuid.UUID] = []


class InternalMessageIn(BaseModel):
    content: str
    sources: list[MessageSourceIn] = []


class DocumentPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_number: int
    width: int | None
    height: int | None
    content: str | None
    has_screenshot: bool
    bounding_boxes: list[BoundingBoxOut]
    predictions: list[DocumentPredictionSummaryOut]


class DocumentPageViewOut(BaseModel):
    """Une page avec de quoi l'afficher (texte, zones normalisées, présence
    d'une capture) et le nom de son document : lecture d'une source citée
    dans le chat."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_number: int
    width: int | None
    height: int | None
    content: str | None
    has_screenshot: bool
    bounding_boxes: list[BoundingBoxOut]
    document_id: uuid.UUID
    document_name: str


class DossierDocumentIn(BaseModel):
    name: str
    size: int
    s3_key: str
    mimetype: str


class DocumentSummaryOut(BaseModel):
    """Résumé d'un document (version individuelle). Append-only : chaque
    régénération crée une nouvelle ligne, la dernière fait foi."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content: str
    model: str | None
    created_at: datetime


class DossierSummaryOut(BaseModel):
    """Résumé global d'un dossier. Append-only : chaque régénération crée
    une nouvelle ligne, la dernière fait foi."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content: str
    model: str | None
    created_at: datetime


class SummaryDepositIn(BaseModel):
    """Payload pour déposer un résumé (worker → backend). Le `model`
    optionnel permet de tracer quel LLM a produit le résumé."""

    content: str
    model: str | None = None


class SummaryStatusIn(BaseModel):
    """Payload pour mettre à jour le statut de génération d'un résumé
    (worker → backend)."""

    status: SummaryStatus
    error: str | None = None


class FileHashIn(BaseModel):
    """Payload pour déposer le hash SHA-256 d'un document (worker
    document_process → backend)."""

    file_hash: str


class SuggestionDepositIn(BaseModel):
    """Payload pour déposer les suggestions d'analyse d'un dossier « à
    ranger » (worker → backend, issue #54)."""

    suggestions: list[dict]


class SuggestionStatusIn(BaseModel):
    """Payload pour mettre à jour le statut de génération des suggestions
    (worker → backend, issue #54)."""

    status: SuggestionStatus
    error: str | None = None


class DossierAssignIn(BaseModel):
    """Payload pour valider le rattachement d'un dossier « à ranger » à une
    analyse (frontend → backend, issue #54)."""

    analyse_id: uuid.UUID


class DossierDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dossier_id: uuid.UUID
    name: str
    size: int
    s3_key: str
    mimetype: str
    label: str | None
    text_extraction_status: TextExtractionStatus
    text_extraction_error: str | None
    file_hash: str | None
    summary_status: SummaryStatus
    summary_error: str | None
    # Dernier résumé généré (le plus récent par created_at), ou None si
    # aucun résumé n'a encore été produit avec succès.
    summary: "DocumentSummaryOut | None" = None
    pages: list[DocumentPageOut]


class DossierDocumentLabelIn(BaseModel):
    label: str | None


class TextExtractionStatusIn(BaseModel):
    status: TextExtractionStatus
    error: str | None = None


class MessageSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dossier_document_id: uuid.UUID | None
    execution_step_id: uuid.UUID | None
    excerpt: str | None
    pages: list[DocumentPageSummaryOut]
    bounding_boxes: list[BoundingBoxOut]


class MessageIn(BaseModel):
    content: str


class ConversationModelUpdate(BaseModel):
    # Identifiant de modèle tel que renvoyé par GET /models ; None = pas de
    # préférence, le hub par défaut sera utilisé.
    model: str | None


class FeedbackIn(BaseModel):
    value: FeedbackValue
    # Uniquement pertinent pour un pouce bas - jamais requis, un pouce haut
    # simple n'a aucune raison.
    reasons: list[FeedbackReasonCode] = []
    comment: str | None = None


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    value: FeedbackValue
    reasons: list[FeedbackReasonCode]
    comment: str | None
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime
    sources: list[MessageSourceOut]
    feedback: FeedbackOut | None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dossier_id: uuid.UUID
    user_id: str
    created_at: datetime
    model: str | None


class MessagePage(BaseModel):
    """Page de messages (curseur) : `items` en ordre chronologique ;
    `has_more` indique qu'il existe des messages plus anciens à charger avec
    `before=<id du premier message>`."""

    items: list[MessageOut]
    has_more: bool


class ChatEventOut(BaseModel):
    """Événement d'exécution du chat (streaming). Déposé par le worker
    pendant l'exécution du graphe LangGraph, consommé par le frontend
    via SSE pour afficher la progression en temps réel."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    kind: ChatEventKind
    data: dict
    created_at: datetime


class ChatEventIn(BaseModel):
    """Payload pour déposer un événement de chat (worker → backend)."""

    kind: ChatEventKind
    data: dict = {}


class ConversationSummaryOut(BaseModel):
    """Vue légère pour la liste "mes conversations" de la sidebar (façon
    ChatGPT) : pas la liste complète des messages, juste de quoi afficher
    une entrée et y naviguer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dossier_id: uuid.UUID
    dossier_name: str
    last_message_preview: str | None
    last_activity_at: datetime


class ExecutionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    level: ExecutionLogLevel
    message: str
    created_at: datetime


class ExecutionStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ExecutionStepKind
    label: str
    status: ExecutionStepStatus
    started_at: datetime
    ended_at: datetime | None
    output: str | None
    logs: list[ExecutionLogOut]


class ExecutionStepCompleteIn(BaseModel):
    status: ExecutionStepStatus
    output: str | None = None


class ExecutionLogIn(BaseModel):
    level: ExecutionLogLevel = ExecutionLogLevel.INFO
    message: str


class DossierCreate(BaseModel):
    name: str
    # Optionnel (issue #54) : un dossier « à ranger » n'a pas d'analyse
    # assignée à la création. Les suggestions d'analyse sont générées après
    # upload des documents et génération des résumés.
    analyse_id: uuid.UUID | None = None
    # Accès (issue #177). Absent : « restricted » aux groupes de la personne qui crée. « restricted » demande au
    # moins un groupe, **parmi les siens** ; « analyse » ouvre le dossier à tous ceux qui ont accès à l'analyse.
    visibility: Literal["restricted", "analyse"] | None = None
    group_paths: list[str] | None = None


class DossierGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    path: str = Field(validation_alias="keycloak_group")
    granted_by: str | None
    created_at: datetime


class DossierAccessOut(BaseModel):
    """Qui voit le dossier : sa visibilité et ses groupes. Lisible par ceux qui voient le dossier ; seuls les
    administrateurs la modifient (``can_edit``)."""

    visibility: Literal["restricted", "analyse"]
    groups: list[DossierGroupOut]
    can_edit: bool
    # Groupes que la personne connectée peut associer : les siens (pas d'appel à Keycloak, pas d'héritage).
    available_groups: list[str]


class DossierAccessUpdate(BaseModel):
    visibility: Literal["restricted", "analyse"]
    # Groupes associés, en remplacement. Un groupe déjà associé se garde ou se retire librement ; un nouveau doit
    # faire partie des groupes de la personne qui modifie.
    group_paths: list[str] = Field(default_factory=list, max_length=50)


class DossierAccessChangeOut(DossierAccessOut):
    # Vrai si le changement a annulé l'affectation d'une personne qui perdait l'accès (avec ``dry_run`` : si elle
    # serait annulée), et qui.
    assignee_unassigned: bool = False
    unassigned_person: "PersonOut | None" = None


class BulkAccessUpdate(DossierAccessUpdate):
    # Plafond : une seule transaction ; une page du tableau de suivi en compte 100 au plus.
    dossier_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class BulkAccessResult(BaseModel):
    """``updated`` : dossiers dont l'accès a changé ; ``unchanged`` : déjà tels quels ; ``unassigned`` : dossiers dont
    la personne affectée a perdu l'accès et a été désaffectée."""

    updated: int
    unchanged: int
    unassigned: int


# --- Schémas internes (worker agent_execution) ---
# Ces schémas exposent les clés S3 (screenshot_key) et les définitions
# d'analyse (labels/entités/prompts) dont le worker a besoin pour
# télécharger les captures et exécuter la classification/extraction.
# Ils ne sont jamais renvoyés par l'API publique (seulement par
# /api/internal/*), pour ne pas fuiter les clés S3 côté frontend.


class InternalDocumentPageOut(BaseModel):
    """Page avec sa clé S3 de capture et ses prédictions (labels + entités)
    - réservé à l'API interne. Les prédictions sont nécessaires pour que
    l'agent LangGraph puisse consulter les classifications et entités déjà
    déposées par les tâches de classification/extraction."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_number: int
    content: str | None
    screenshot_key: str | None
    predictions: list[DocumentPredictionSummaryOut] = []


class InternalDossierDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    s3_key: str
    mimetype: str
    text_extraction_status: TextExtractionStatus
    file_hash: str | None = None
    summary_status: SummaryStatus = SummaryStatus.EN_ATTENTE
    summary: DocumentSummaryOut | None = None
    pages: list[InternalDocumentPageOut]


class InternalExecutionStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ExecutionStepKind
    label: str
    status: ExecutionStepStatus
    # Synthèse produite par l'agent (si output=True et étape terminée).
    # Nécessaire au chat pour injecter les synthèses existantes dans le
    # contexte de la conversation.
    output: str | None = None


class InternalMessageOut(BaseModel):
    """Message de conversation pour le worker (chat). Inclut le rôle et le
    contenu, sans les sources (le worker n'en a pas besoin pour construire
    son contexte - il génère les siennes)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime


class InternalConversationOut(BaseModel):
    """Conversation complète pour le worker : messages (historique du chat)
    + modèle LLM préféré. Le worker en a besoin pour construire le contexte
    du graphe LangGraph de chat."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dossier_id: uuid.UUID
    # Utilisateur propriétaire de la conversation : le chat propose des
    # modifications de l'analyse pour son compte.
    user_id: str
    model: str | None
    messages: list[InternalMessageOut]


class InternalDossierOut(BaseModel):
    """Dossier complet pour le worker : documents, pages (avec clés S3),
    étapes d'exécution. Pas de prédictions ici - le worker en dépose, il
    n'a pas besoin de les lire."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analyse_id: uuid.UUID | None
    status: DossierStatus
    summary_status: SummaryStatus = SummaryStatus.EN_ATTENTE
    summary: DossierSummaryOut | None = None
    suggested_analyses: list[dict] | None = None
    suggestion_status: SuggestionStatus = SuggestionStatus.EN_ATTENTE
    execution_steps: list[InternalExecutionStepOut]
    documents: list[InternalDossierDocumentOut]


class InternalLabelDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    definition: str


class InternalEntityDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    definition: str
    type: str


class InternalClassificationOut(BaseModel):
    prompt: str
    labels: list[InternalLabelDefinitionOut]


class InternalExtractionOut(BaseModel):
    prompt: str
    entities: list[InternalEntityDefinitionOut]


class InternalAgentOut(BaseModel):
    """Définition d'un agent pour le worker : prompt, outils, output, modèle.
    L'agent LangGraph utilise ces informations pour configurer son graphe."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prompt: str
    tools: list[str]
    output: bool
    model: str | None


class InternalAnalyseOut(BaseModel):
    """Définitions de l'analyse (labels, entités, prompts, agents) pour le
    worker. Les agents sont gérés par la tâche LangGraph qui les exécute
    un par un après la classification et l'extraction."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    classification: InternalClassificationOut
    extraction: InternalExtractionOut
    agents: list[InternalAgentOut] = []


class WorkflowStatusUpdate(BaseModel):
    status_id: uuid.UUID


class PersonOut(BaseModel):
    """Une personne de l'annuaire local (#173) : identifiant Keycloak et nom affiché. Pas d'e-mail : un dossier
    n'a pas à le diffuser."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class AssigneeUpdate(BaseModel):
    """Nouvelle personne responsable du dossier ; ``null`` le désaffecte."""

    assignee_id: str | None


class BulkAssigneeUpdate(AssigneeUpdate):
    # Plafond : l'affectation en lot est une seule transaction, et une page du tableau de suivi en compte 100 au plus.
    dossier_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class BulkAssigneeResult(BaseModel):
    """``updated`` : dossiers dont le responsable a changé ; ``unchanged`` : déjà affectés à cette personne."""

    updated: int
    unchanged: int


class CustomValueIn(BaseModel):
    """Nouvelle valeur d'une colonne personnalisée (issue #173) ; ``null`` ou une chaîne vide l'efface."""

    value: Any = None


class CustomValueOut(BaseModel):
    field_id: str
    value: Any = None


class DueAtUpdate(BaseModel):
    """Nouvelle échéance du dossier ; ``null`` la supprime."""

    due_at: date | None


class DueInfoOut(BaseModel):
    """Situation du dossier par rapport à son échéance, calculée côté serveur selon les seuils de l'analyse.

    ``level`` : ``ok`` (loin), ``soon`` (proche), ``overdue`` (dépassée), ``closed`` (clos : plus à surveiller).
    ``color`` : couleur du niveau selon les seuils (``null`` pour un dossier clos). ``days_left`` : jours
    restants, négatif si l'échéance est dépassée."""

    model_config = ConfigDict(from_attributes=True)

    level: str
    days_left: int
    color: str | None


class DossierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    analyse_id: uuid.UUID | None
    analyse_version: str
    created_at: datetime
    status: DossierStatus
    started_at: datetime | None
    ended_at: datetime | None
    # Statut de dossier défini par son analyse (issue #168), distinct de `status` (exécution) ;
    # None pour un dossier « à ranger ». `closed_at` : date de clôture (statut final), ou None.
    workflow_status: StatusDefinitionOut | None = None
    closed_at: datetime | None = None
    # Qui voit le dossier (#177) : « restricted » (groupes associés) ou « analyse ».
    visibility: Literal["restricted", "analyse"] = "analyse"
    # Valeurs des colonnes personnalisées du suivi (#173) : {identifiant du champ: valeur}. Les définitions sont sur
    # l'analyse (`GET /api/analyses/{id}`).
    custom_values: dict[str, Any] = {}
    # Responsable du dossier (#173), ``null`` si non affecté, et depuis quand.
    assignee: PersonOut | None = None
    assigned_at: datetime | None = None
    # Échéance (issue #172) : la date, son niveau calculé par le serveur, et « clos avant l'échéance » (``null``
    # si le dossier n'est pas clos ou n'a pas d'échéance).
    due_at: date | None = None
    due: DueInfoOut | None = None
    closed_before_due: bool | None = None
    summary_status: SummaryStatus
    summary_error: str | None
    # Dernier résumé global du dossier (le plus récent), ou None.
    summary: "DossierSummaryOut | None" = None
    # Suggestions d'analyse pour un dossier « à ranger » (issue #54).
    suggested_analyses: list[dict] | None = None
    suggestion_status: SuggestionStatus
    execution_steps: list[ExecutionStepOut]
    documents: list[DossierDocumentOut]
