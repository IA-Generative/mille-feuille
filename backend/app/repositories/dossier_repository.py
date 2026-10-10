import asyncio
import uuid
from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.connectors import s3_connector
from app.models.analyse import Analyse, StatusDefinition
from app.models.app_user import AppUser
from app.models.chat_event import ChatEvent, ChatEventKind
from app.models.conversation import (
    Conversation,
    Message,
    MessageRole,
    MessageSource,
    message_source_bounding_boxes,
    message_source_pages,
)
from app.models.document_page import (
    BoundingBox,
    DocumentPage,
    DocumentPrediction,
    PredictionKind,
    PredictionValidationStatus,
    prediction_bounding_boxes,
    prediction_pages,
)
from app.models.dossier import (
    Dossier,
    DossierDocument,
    DossierStatus,
    ExecutionStep,
    ExecutionStepKind,
    ExecutionStepStatus,
    SuggestionStatus,
    TextExtractionStatus,
)
from app.models.dossier_access import DossierGroupAccess, Visibility
from app.models.dossier_analysis import AnalysisElement, AnalysisElementVersion
from app.models.dossier_event import DossierEventType
from app.models.execution_log import ExecutionLog, ExecutionLogLevel
from app.models.feedback import (
    Feedback,
    FeedbackReason,
    FeedbackReasonCode,
    FeedbackValue,
)
from app.models.generated_document import GeneratedDocument
from app.models.summary import (
    DocumentSummary,
    DossierSummary,
    SummaryStatus,
)
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.repositories.dossier_event_repository import DossierEventRepository
from app.services.custom_fields import default_values
from app.services.dossier_access import visible_clause
from app.services.due_date import today_in_paris
from app.services.prediction_validation import record_validation


def _validations_load(parent, *, chained: bool = False):
    """Chargement de l'historique de validation d'une prédiction (issue #120) :
    ses éléments d'analyse, leurs versions et la zone corrigée de chacune.
    ``parent`` est le chargement de la prédiction ; avec ``chained``, il porte
    déjà le chargement de ses éléments d'analyse."""
    elements = parent if chained else parent.selectinload(DocumentPrediction.analysis_elements)
    return elements.selectinload(AnalysisElement.versions).selectinload(AnalysisElementVersion.bounding_box)


if TYPE_CHECKING:
    from app.core.security.factory import RequestContext


class DossierRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._analyse_repository = AnalyseRepository(db)
        self.events = DossierEventRepository(db)

    def _base_query(self):
        pages_load = selectinload(Dossier.documents).selectinload(DossierDocument.pages)
        predictions_load = pages_load.selectinload(DocumentPage.predictions)
        return (
            select(Dossier)
            .options(
                selectinload(Dossier.execution_steps).selectinload(ExecutionStep.logs),
                pages_load.selectinload(DocumentPage.bounding_boxes),
                predictions_load.selectinload(DocumentPrediction.bounding_boxes),
                _validations_load(predictions_load),
                # Résumés du dossier + résumés de chaque document (issue #52).
                selectinload(Dossier.summaries),
                selectinload(Dossier.documents).selectinload(DossierDocument.summaries),
                # populate_existing: nécessaire pour le SSE (/dossiers/{id}/stream),
                # qui réinterroge en boucle sur la même session - sans ça, une
                # fois le Dossier chargé une première fois, les requêtes
                # suivantes renverraient l'objet du cache d'identité, pas l'état
                # réellement en base.
            )
            .execution_options(populate_existing=True)
        )

    async def list_all(self) -> Sequence[Dossier]:
        result = await self.db.execute(self._base_query().order_by(Dossier.created_at.desc()))
        return result.scalars().all()

    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        workflow_status_id: uuid.UUID | None = None,
        due: str | None = None,
        assignee: str | None = None,
        sort: str = "created_at",
        user: "RequestContext | None" = None,
    ) -> tuple[Sequence[Dossier], int]:
        """Liste paginée, du plus récent au plus ancien par défaut.

        - ``workflow_status_id`` : ne garde que les dossiers de ce statut (issue #170) ;
        - ``due`` : filtre d'échéance, ne garde que les dossiers **non clos** (``overdue`` : échéance dépassée ;
          ``7`` / ``30`` : dans 7 / 30 jours ou moins ; ``none`` : sans échéance) ;
        - ``assignee`` : ``none`` (non affectés) ou l'identifiant d'une personne (#173) ;
        - ``sort="status"`` : trie par statut, dans l'ordre défini par chaque analyse (les dossiers sans
          statut en dernier), puis du plus récent au plus ancien ;
        - ``sort="due"`` : échéance la plus proche d'abord (sans échéance en dernier).
        """
        filters = [Dossier.workflow_status_id == workflow_status_id] if workflow_status_id else []
        if user is not None:
            filters.append(visible_clause(user.is_admin, user.groups))
        filters += self._due_filters(due)
        if assignee == "none":
            filters.append(Dossier.assignee_id.is_(None))
        elif assignee:
            filters.append(Dossier.assignee_id == assignee)
        total = await self.db.scalar(select(func.count()).select_from(Dossier).where(*filters))
        query = self._base_query().where(*filters)
        if sort == "due":
            query = query.order_by(Dossier.due_at.asc().nulls_last(), Dossier.created_at.desc())
        elif sort == "status":
            query = query.outerjoin(StatusDefinition, StatusDefinition.id == Dossier.workflow_status_id).order_by(
                StatusDefinition.position.asc().nulls_last(), Dossier.created_at.desc()
            )
        else:
            query = query.order_by(Dossier.created_at.desc())
        result = await self.db.execute(query.limit(page_size).offset((page - 1) * page_size))
        return result.scalars().all(), total or 0

    @staticmethod
    def _due_filters(due: str | None) -> list:
        """Conditions SQL d'un filtre d'échéance (jour courant à Paris). Un dossier clos n'est plus à surveiller."""
        if due is None:
            return []
        today = today_in_paris()
        if due == "none":
            return [Dossier.due_at.is_(None)]
        open_dossier = Dossier.closed_at.is_(None)
        if due == "overdue":
            return [open_dossier, Dossier.due_at < today]
        days = int(due)  # « 7 » ou « 30 » : valeurs contrôlées par la route
        return [open_dossier, Dossier.due_at >= today, Dossier.due_at <= today + timedelta(days=days)]

    async def get(self, dossier_id: uuid.UUID, user: "RequestContext | None" = None) -> Dossier | None:
        """Le dossier, ou ``None`` s'il n'existe pas **ou n'est pas visible de ``user``** (issue #177 : même réponse,
        pour ne pas révéler l'existence d'un dossier restreint). Sans ``user`` : appel interne, pas de filtre."""
        query = self._base_query().where(Dossier.id == dossier_id)
        if user is not None:
            query = query.where(visible_clause(user.is_admin, user.groups))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        name: str,
        analyse: Analyse | None = None,
        actor=None,
        visibility: Visibility = Visibility.ANALYSE,
        group_paths: Collection[str] = (),
    ) -> Dossier:
        """Crée le dossier. ``visibility`` « analyse » par défaut (appels programmatiques : MCP, runs éphémères) ;
        la route des utilisateurs crée des dossiers restreints, avec leurs groupes (issue #177)."""
        dossier = Dossier(
            name=name,
            visibility=visibility.value,
            analyse_id=analyse.id if analyse else None,
            analyse_version=self._analyse_repository.get_version_label(analyse) if analyse else "v1",
            status=DossierStatus.EN_ATTENTE,
            # Statut initial de l'analyse (issue #168) ; rien pour un dossier « à ranger ».
            workflow_status_id=self._initial_status_id(analyse),
            due_at=self._default_due_at(analyse),
            # Valeur par défaut de chaque colonne personnalisée de l'analyse (#173).
            custom_values=default_values(analyse.custom_fields) if analyse else {},
        )
        self.db.add(dossier)
        await self.db.flush()  # donne son identifiant au dossier, que l'événement référence
        for path in sorted(set(group_paths)):
            self.db.add(
                DossierGroupAccess(
                    dossier_id=dossier.id, keycloak_group=path, granted_by=getattr(actor, "user_id", None)
                )
            )
        self.events.add(
            dossier.id,
            DossierEventType.CREATED,
            actor,
            {
                "analyse_id": str(analyse.id) if analyse else None,
                "visibility": visibility.value,
                **({"groups": sorted(set(group_paths))} if group_paths else {}),
                **({"due_at": dossier.due_at.isoformat()} if dossier.due_at else {}),
            },
        )
        await self.db.commit()
        await self.db.refresh(dossier)
        return dossier

    @staticmethod
    def _default_due_at(analyse: Analyse | None) -> date | None:
        """Échéance d'un dossier qui rejoint l'analyse : aujourd'hui + sa durée par défaut, s'il y en a une."""
        if analyse is None or analyse.default_due_days is None:
            return None
        return today_in_paris() + timedelta(days=analyse.default_due_days)

    async def set_custom_value(self, dossier: Dossier, field: dict, value, actor=None) -> bool:
        """Pose la valeur d'une colonne personnalisée (``None`` l'efface) et la trace dans le journal (#169) :
        ancienne et nouvelle valeur, auteur. Sans changement, rien n'est écrit ; renvoie si la valeur a changé."""
        current = dict(dossier.custom_values or {})
        previous = current.get(field["id"])
        if previous == value and type(previous) is type(value):
            return False
        if value is None:
            current.pop(field["id"], None)
        else:
            current[field["id"]] = value
        dossier.custom_values = current
        self.events.add(
            dossier.id,
            DossierEventType.CUSTOM_VALUE_CHANGED,
            actor,
            {"field": {"id": field["id"], "name": field["name"]}, "from": previous, "to": value},
        )
        await self.db.commit()
        return True

    async def set_due_at(self, dossier: Dossier, due_at: date | None, actor=None, reason: str | None = None) -> None:
        """Change l'échéance du dossier (ou la supprime avec ``None``) et trace le changement dans le journal (#169)."""
        if dossier.due_at == due_at:
            return
        payload: dict = {
            "from": dossier.due_at.isoformat() if dossier.due_at else None,
            "to": due_at.isoformat() if due_at else None,
        }
        if reason:
            payload["reason"] = reason
        dossier.due_at = due_at
        self.events.add(dossier.id, DossierEventType.DUE_DATE_CHANGED, actor, payload)
        await self.db.commit()

    async def set_assignee(self, dossier: Dossier, assignee: AppUser | None, actor=None) -> bool:
        """Affecte le dossier à une personne de l'annuaire (ou le désaffecte avec ``None``) et trace le changement
        dans le journal (#169). Sans changement, rien n'est écrit ; renvoie si le dossier a changé."""
        if self._apply_assignee(dossier, assignee, actor):
            await self.db.commit()
            return True
        return False

    async def assign_many(self, dossiers: Sequence[Dossier], assignee: AppUser | None, actor=None) -> int:
        """Affectation en lot : **tout ou rien** (une seule transaction). Renvoie le nombre de dossiers modifiés."""
        changed = sum(self._apply_assignee(dossier, assignee, actor) for dossier in dossiers)
        if changed:
            await self.db.commit()
        return changed

    def _apply_assignee(self, dossier: Dossier, assignee: AppUser | None, actor, reason: str | None = None) -> bool:
        previous = dossier.assignee
        if (previous.user_id if previous else None) == (assignee.user_id if assignee else None):
            return False
        self.events.add(
            dossier.id,
            DossierEventType.ASSIGNEE_CHANGED,
            actor,
            {
                "from": self._person_ref(previous),
                "to": self._person_ref(assignee),
                **({"reason": reason} if reason else {}),
            },
        )
        dossier.assignee_id = assignee.user_id if assignee else None
        dossier.assignee = assignee
        dossier.assigned_at = datetime.now(UTC) if assignee else None
        return True

    @staticmethod
    def _person_ref(person: AppUser | None) -> dict | None:
        return {"id": person.user_id, "name": person.name} if person else None

    async def get_many(self, dossier_ids: Sequence[uuid.UUID], user: "RequestContext | None" = None) -> list[Dossier]:
        query = self._base_query().where(Dossier.id.in_(dossier_ids))
        if user is not None:
            query = query.where(visible_clause(user.is_admin, user.groups))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def _initial_status_id(self, analyse: Analyse | None) -> uuid.UUID | None:
        initial = self._analyse_repository.initial_status(analyse) if analyse else None
        return initial.id if initial else None

    async def set_workflow_status(self, dossier: Dossier, status: StatusDefinition, actor=None) -> None:
        """Change le statut de dossier (issue #168). Le statut doit appartenir à l'analyse du dossier
        (vérifié par l'appelant). Un statut final pose la date de clôture (conservée d'un statut final à
        un autre) ; tout autre statut l'efface.
        Le changement est tracé dans le journal du dossier (#169) : changement de statut, et clôture ou réouverture."""
        previous = dossier.workflow_status
        was_closed = dossier.closed_at is not None
        dossier.workflow_status_id = status.id
        if status.is_final:
            if dossier.closed_at is None:
                dossier.closed_at = datetime.now(UTC)
        else:
            dossier.closed_at = None
        if previous is None or previous.id != status.id:
            self.events.add(
                dossier.id,
                DossierEventType.STATUS_CHANGED,
                actor,
                {
                    "from": {"id": str(previous.id), "name": previous.name} if previous else None,
                    "to": {"id": str(status.id), "name": status.name},
                },
            )
        if not was_closed and dossier.closed_at is not None:
            self.events.add(
                dossier.id, DossierEventType.CLOSED, actor, {"status": {"id": str(status.id), "name": status.name}}
            )
        elif was_closed and dossier.closed_at is None:
            self.events.add(
                dossier.id, DossierEventType.REOPENED, actor, {"status": {"id": str(status.id), "name": status.name}}
            )
        await self.db.commit()

    async def add_documents(self, dossier: Dossier, documents: list[dict]) -> list[DossierDocument]:
        created = [
            DossierDocument(
                dossier_id=dossier.id,
                name=document["name"],
                size=document["size"],
                s3_key=document["s3_key"],
                mimetype=document["mimetype"],
            )
            for document in documents
        ]
        for document in created:
            self.db.add(document)
        await self.db.commit()
        await self.db.refresh(dossier)
        return created

    async def set_text_extraction_status(
        self,
        document: DossierDocument,
        status: TextExtractionStatus,
        error: str | None = None,
    ) -> None:
        document.text_extraction_status = status
        document.text_extraction_error = error
        await self.db.commit()

    async def set_document_label(self, document: DossierDocument, label: str | None) -> None:
        document.label = label
        await self.db.commit()
        # Pas de refresh(document) : réexpirerait `pages` (déjà chargée par
        # get_document) et redéclencherait un lazy-load hors contexte async.

    def _conversation_query(self, *, with_messages: bool = True):
        # populate_existing: without it, re-querying a Conversation already in
        # the identity map (e.g. right after adding a message to it) would
        # keep the stale, already-loaded `messages` collection instead of
        # picking up the row just committed.
        # with_messages=False : les listes de conversations n'ont pas besoin
        # de l'historique (les messages se lisent par page via list_messages_page).
        options = []
        if with_messages:
            sources_load = selectinload(Conversation.messages).selectinload(Message.sources)
            feedback_load = (
                selectinload(Conversation.messages).selectinload(Message.feedbacks).selectinload(Feedback.reason_rows)
            )
            options = [
                sources_load.selectinload(MessageSource.pages),
                sources_load.selectinload(MessageSource.bounding_boxes),
                feedback_load,
            ]
        return select(Conversation).options(*options).execution_options(populate_existing=True)

    async def list_messages_page(
        self, conversation_id: uuid.UUID, *, limit: int, before_id: uuid.UUID | None = None
    ) -> tuple[list[Message], bool]:
        """Page de messages par curseur, du plus récent vers l'ancien : les
        `limit` messages précédant `before_id` (ou les plus récents si absent).
        Renvoyés en ordre chronologique, avec `has_more` si des messages plus
        anciens existent."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .options(
                selectinload(Message.sources).selectinload(MessageSource.pages),
                selectinload(Message.sources).selectinload(MessageSource.bounding_boxes),
                selectinload(Message.feedbacks).selectinload(Feedback.reason_rows),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit + 1)
        )
        if before_id is not None:
            cursor = (
                await self.db.execute(
                    select(Message.created_at, Message.id).where(
                        Message.id == before_id, Message.conversation_id == conversation_id
                    )
                )
            ).one_or_none()
            if cursor is not None:
                stmt = stmt.where(
                    (Message.created_at < cursor.created_at)
                    | ((Message.created_at == cursor.created_at) & (Message.id < cursor.id))
                )
        rows = list((await self.db.execute(stmt)).scalars().all())
        has_more = len(rows) > limit
        return list(reversed(rows[:limit])), has_more

    async def list_conversations(self, dossier_id: uuid.UUID, user_id: str) -> Sequence[Conversation]:
        result = await self.db.execute(
            self._conversation_query(with_messages=False)
            .where(Conversation.dossier_id == dossier_id, Conversation.user_id == user_id)
            .order_by(Conversation.created_at)
        )
        return result.scalars().all()

    async def list_conversations_paginated(
        self, *, dossier_id: uuid.UUID, user_id: str, page: int, page_size: int
    ) -> tuple[Sequence[Conversation], int]:
        base = self._conversation_query(with_messages=False).where(
            Conversation.dossier_id == dossier_id, Conversation.user_id == user_id
        )
        count_query = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.dossier_id == dossier_id, Conversation.user_id == user_id)
        )
        total = await self.db.scalar(count_query)
        result = await self.db.execute(
            base.order_by(Conversation.created_at).limit(page_size).offset((page - 1) * page_size)
        )
        return result.scalars().all(), total or 0

    def _dossier_predictions_filter(self, dossier_id: uuid.UUID, kind: PredictionKind):
        """Prédictions d'un type dont au moins une page appartient à un document du dossier."""
        return DocumentPrediction.kind == kind, DocumentPrediction.id.in_(
            select(prediction_pages.c.prediction_id)
            .join(DocumentPage, DocumentPage.id == prediction_pages.c.document_page_id)
            .join(DossierDocument, DossierDocument.id == DocumentPage.dossier_document_id)
            .where(DossierDocument.dossier_id == dossier_id)
        )

    async def list_predictions_paginated(
        self, *, dossier_id: uuid.UUID, kind: PredictionKind, page: int, page_size: int
    ) -> tuple[Sequence[DocumentPrediction], int]:
        """Détail paginé des classifications (LABEL) ou entités (ENTITY) d'un dossier, avec les pages et leur
        document pour situer chaque résultat. Ordre stable : nom puis création."""
        conditions = self._dossier_predictions_filter(dossier_id, kind)
        total = await self.db.scalar(select(func.count()).select_from(DocumentPrediction).where(*conditions))
        result = await self.db.execute(
            select(DocumentPrediction)
            .options(selectinload(DocumentPrediction.pages).selectinload(DocumentPage.document))
            .where(*conditions)
            .order_by(DocumentPrediction.name, DocumentPrediction.created_at, DocumentPrediction.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return result.scalars().all(), total or 0

    async def results_breakdown(self, dossier_id: uuid.UUID) -> list[dict]:
        """Par fichier : nombre de pages, pages classifiées et entités extraites."""
        documents = (
            await self.db.execute(
                select(DossierDocument.id, DossierDocument.name, func.count(DocumentPage.id))
                .outerjoin(DocumentPage, DocumentPage.dossier_document_id == DossierDocument.id)
                .where(DossierDocument.dossier_id == dossier_id)
                .group_by(DossierDocument.id, DossierDocument.name, DossierDocument.created_at)
                .order_by(DossierDocument.created_at, DossierDocument.id)
            )
        ).all()

        async def count_by_document(kind: PredictionKind, distinct_column) -> dict[uuid.UUID, int]:
            rows = await self.db.execute(
                select(DocumentPage.dossier_document_id, func.count(func.distinct(distinct_column)))
                .select_from(prediction_pages)
                .join(DocumentPage, DocumentPage.id == prediction_pages.c.document_page_id)
                .join(DocumentPrediction, DocumentPrediction.id == prediction_pages.c.prediction_id)
                .join(DossierDocument, DossierDocument.id == DocumentPage.dossier_document_id)
                .where(DossierDocument.dossier_id == dossier_id, DocumentPrediction.kind == kind)
                .group_by(DocumentPage.dossier_document_id)
            )
            return {document_id: count for document_id, count in rows.all()}

        classified = await count_by_document(PredictionKind.LABEL, DocumentPage.id)
        entities = await count_by_document(PredictionKind.ENTITY, DocumentPrediction.id)
        return [
            {
                "document_id": document_id,
                "document_name": name,
                "page_count": page_count,
                "classified_page_count": classified.get(document_id, 0),
                "entity_count": entities.get(document_id, 0),
            }
            for document_id, name, page_count in documents
        ]

    async def list_conversations_for_user(self, user_id: str) -> Sequence[Conversation]:
        """Toutes les conversations de l'utilisateur, tous dossiers confondus,
        triées par activité la plus récente (dernier message). Utilisé par la
        sidebar /api/conversations (ConversationSummaryOut)."""
        result = await self.db.execute(
            select(Conversation)
            .join(Dossier, Conversation.dossier_id == Dossier.id)
            .options(
                selectinload(Conversation.dossier),
                selectinload(Conversation.messages),
            )
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at)
        )
        conversations = result.scalars().all()
        # Tri Python par dernier message (created_at) décroissant : les
        # conversations sans message vont en fin de liste.
        conversations.sort(
            key=lambda c: c.messages[-1].created_at if c.messages else c.created_at,
            reverse=True,
        )
        return conversations

    async def list_conversations_for_user_paginated(
        self, *, user_id: str, page: int, page_size: int, user: "RequestContext | None" = None
    ) -> tuple[Sequence[Conversation], int]:
        """Version paginée de list_conversations_for_user, triée par activité
        la plus récente (dernier message created_at, ou created_at de la
        conversation si pas de message)."""
        # Sous-requête : timestamp du dernier message par conversation.
        last_msg = (
            select(Message.conversation_id, func.max(Message.created_at).label("last_at"))
            .group_by(Message.conversation_id)
            .subquery()
        )
        # Une conversation sur un dossier qu'on ne voit plus n'est plus listée (issue #177).
        visible = [visible_clause(user.is_admin, user.groups)] if user is not None else []
        count_query = (
            select(func.count())
            .select_from(Conversation)
            .join(Dossier, Conversation.dossier_id == Dossier.id)
            .where(Conversation.user_id == user_id, *visible)
        )
        total = await self.db.scalar(count_query)
        result = await self.db.execute(
            select(Conversation)
            .join(Dossier, Conversation.dossier_id == Dossier.id)
            .outerjoin(last_msg, last_msg.c.conversation_id == Conversation.id)
            .options(
                selectinload(Conversation.dossier),
                selectinload(Conversation.messages),
            )
            .where(Conversation.user_id == user_id, *visible)
            .order_by(func.coalesce(last_msg.c.last_at, Conversation.created_at).desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return result.scalars().all(), total or 0

    async def get_conversation(self, conversation_id: uuid.UUID) -> Conversation | None:
        result = await self.db.execute(self._conversation_query().where(Conversation.id == conversation_id))
        return result.scalar_one_or_none()

    async def create_conversation(self, dossier_id: uuid.UUID, user_id: str) -> Conversation:
        # Idempotent : si une conversation existe déjà pour ce couple
        # (dossier, utilisateur), on la renvoie au lieu d'en créer une
        # nouvelle. La page dossier est un chat personnel par instructeur :
        # cliquer plusieurs fois sur le dossier ne doit pas dupliquer la
        # conversation.
        existing = await self.list_conversations(dossier_id, user_id)
        if existing:
            return existing[0]

        conversation = Conversation(dossier_id=dossier_id, user_id=user_id)
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return await self.get_conversation(conversation.id)

    async def delete_conversation(self, conversation: Conversation) -> None:
        await self.db.delete(conversation)
        await self.db.commit()

    async def update_conversation_model(self, conversation: Conversation, model: str | None) -> Conversation:
        conversation.model = model
        await self.db.commit()
        await self.db.refresh(conversation)
        return await self.get_conversation(conversation.id)

    async def add_message(
        self,
        conversation: Conversation,
        role: MessageRole,
        content: str,
        sources: list[dict] | None = None,
    ) -> Conversation:
        message = Message(conversation_id=conversation.id, role=role, content=content)
        self.db.add(message)
        await self.db.flush()
        for source in sources or []:
            message_source = MessageSource(
                message_id=message.id,
                dossier_document_id=source.get("dossier_document_id"),
                execution_step_id=source.get("execution_step_id"),
                excerpt=source.get("excerpt"),
            )
            self.db.add(message_source)
            await self.db.flush()
            page_ids = source.get("page_ids") or []
            if page_ids:
                await self.db.execute(
                    insert(message_source_pages),
                    [
                        {
                            "message_source_id": message_source.id,
                            "document_page_id": pid,
                        }
                        for pid in page_ids
                    ],
                )
            bounding_box_ids = source.get("bounding_box_ids") or []
            if bounding_box_ids:
                await self.db.execute(
                    insert(message_source_bounding_boxes),
                    [{"message_source_id": message_source.id, "bounding_box_id": bid} for bid in bounding_box_ids],
                )
        await self.db.commit()
        return await self.get_conversation(conversation.id)

    async def set_feedback(
        self,
        message: Message,
        user_id: str,
        value: FeedbackValue,
        reasons: list[FeedbackReasonCode] | None = None,
        comment: str | None = None,
    ) -> Conversation:
        # Idempotent : un seul retour par (message, utilisateur). On
        # met à jour s'il existe déjà, sinon on en crée un nouveau.
        existing = next((f for f in message.feedbacks if f.user_id == user_id), None)
        if existing is None:
            existing = Feedback(message_id=message.id, user_id=user_id)
            self.db.add(existing)
        existing.value = value
        existing.comment = comment
        await self.db.flush()
        # Replace reasons: delete old, insert new
        await self.db.execute(FeedbackReason.__table__.delete().where(FeedbackReason.feedback_id == existing.id))
        for reason in reasons or []:
            self.db.add(FeedbackReason(feedback_id=existing.id, reason=reason))
        await self.db.commit()
        return await self.get_conversation(message.conversation_id)

    async def delete_feedback(self, message: Message, user_id: str) -> Conversation:
        existing = next((f for f in message.feedbacks if f.user_id == user_id), None)
        if existing is not None:
            await self.db.delete(existing)
            await self.db.commit()
        return await self.get_conversation(message.conversation_id)

    # --- Événements de chat (streaming de l'exécution) ---

    async def add_chat_event(self, conversation_id: uuid.UUID, kind: ChatEventKind, data: dict) -> ChatEvent:
        """Dépose un événement de chat (tool_call, tool_result, thinking,
        done, error). Ces événements sont consommés par le frontend via
        SSE pour streamer la progression de l'exécution en temps réel."""
        event = ChatEvent(conversation_id=conversation_id, kind=kind, data=data)
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def list_chat_events(
        self, conversation_id: uuid.UUID, after_id: uuid.UUID | None = None
    ) -> Sequence[ChatEvent]:
        """Liste les événements de chat d'une conversation, éventuellement
        après un ID donné (pour le SSE : ne renvoyer que les nouveaux
        événements depuis le dernier poll)."""
        stmt = (
            select(ChatEvent)
            .where(ChatEvent.conversation_id == conversation_id)
            .order_by(ChatEvent.created_at, ChatEvent.id)
        )
        if after_id is not None:
            # Récupère les événements créés après after_id. On compare sur
            # (created_at, id) pour garantir l'ordre même si deux événements
            # ont le même timestamp.
            sub = select(ChatEvent.created_at).where(ChatEvent.id == after_id).scalar_subquery()
            stmt = stmt.where(ChatEvent.created_at > sub)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def delete_chat_events(self, conversation_id: uuid.UUID) -> None:
        """Supprime tous les événements de chat d'une conversation. Appelé
        avant une nouvelle exécution pour repartir d'un état propre."""
        await self.db.execute(ChatEvent.__table__.delete().where(ChatEvent.conversation_id == conversation_id))
        await self.db.commit()

    # --- Logs et callback de fin d'étape (appelés par le worker) ---

    async def get_execution_step(self, dossier_id: uuid.UUID, step_id: uuid.UUID) -> ExecutionStep | None:
        result = await self.db.execute(
            select(ExecutionStep)
            .options(selectinload(ExecutionStep.logs))
            .where(ExecutionStep.id == step_id, ExecutionStep.dossier_id == dossier_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_execution_step_by_id(self, step_id: uuid.UUID) -> ExecutionStep | None:
        result = await self.db.execute(
            select(ExecutionStep)
            .options(selectinload(ExecutionStep.logs))
            .where(ExecutionStep.id == step_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def add_log(self, step: ExecutionStep, level: ExecutionLogLevel, message: str) -> ExecutionStep:
        self.db.add(ExecutionLog(execution_step_id=step.id, level=level, message=message))
        await self.db.commit()
        return await self.get_execution_step(step.dossier_id, step.id)

    async def complete_execution_step(
        self, step: ExecutionStep, status: ExecutionStepStatus, output: str | None
    ) -> ExecutionStep:
        step.status = status
        step.output = output
        step.ended_at = datetime.now(UTC)
        await self._complete_dossier_if_all_steps_done(step.dossier_id)
        await self.db.commit()
        # Pas de refresh(step) : réexpirerait `logs` (déjà chargée par
        # get_execution_step_by_id) et redéclencherait un lazy-load hors
        # contexte async à la sérialisation - même raison que add_page.
        return step

    async def _complete_dossier_if_all_steps_done(self, dossier_id: uuid.UUID) -> None:
        """Rien ne faisait jusqu'ici la synthèse "toutes les étapes sont
        terminées -> le Dossier lui-même est terminé" : le worker complète
        chaque ExecutionStep indépendamment (add_log/complete_execution_step
        ci-dessus) mais le Dossier restait en_cours indéfiniment une fois le
        pipeline fini. Fait passer le Dossier à terminé (ou échec si au
        moins une étape a échoué) dès que plus aucune étape n'est en_cours.
        Même transaction que le complete_execution_step qui vient de
        déclencher la vérification : l'autoflush rend la mutation du step
        ci-dessus déjà visible à la requête ci-dessous, pas de commit
        intermédiaire nécessaire."""
        result = await self.db.execute(select(ExecutionStep).where(ExecutionStep.dossier_id == dossier_id))
        steps = result.scalars().all()
        if not steps or any(s.status == ExecutionStepStatus.EN_COURS for s in steps):
            return
        dossier = await self.db.get(Dossier, dossier_id)
        if dossier is None or dossier.status != DossierStatus.EN_COURS:
            return
        dossier.status = (
            DossierStatus.ECHEC if any(s.status == ExecutionStepStatus.ECHEC for s in steps) else DossierStatus.TERMINE
        )
        dossier.ended_at = datetime.now(UTC)
        # Action du système (le worker a terminé) : pas d'auteur. Même transaction que l'étape qui la déclenche.
        self.events.add(
            dossier_id,
            DossierEventType.ANALYSIS_FAILED
            if dossier.status == DossierStatus.ECHEC
            else DossierEventType.ANALYSIS_FINISHED,
        )

    # --- Pages, prédictions et validation humaine ---

    def _document_options(self):
        pages_load = selectinload(DossierDocument.pages)
        predictions_load = pages_load.selectinload(DocumentPage.predictions)
        return (
            pages_load.selectinload(DocumentPage.bounding_boxes),
            predictions_load.selectinload(DocumentPrediction.bounding_boxes),
            _validations_load(predictions_load),
            selectinload(DossierDocument.summaries),
        )

    async def get_document(self, dossier_id: uuid.UUID, document_id: uuid.UUID) -> DossierDocument | None:
        result = await self.db.execute(
            select(DossierDocument)
            .options(*self._document_options())
            .where(
                DossierDocument.id == document_id,
                DossierDocument.dossier_id == dossier_id,
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_document_by_id(self, document_id: uuid.UUID) -> DossierDocument | None:
        result = await self.db.execute(
            select(DossierDocument)
            .options(*self._document_options())
            .where(DossierDocument.id == document_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def add_page(
        self,
        document: DossierDocument,
        *,
        page_number: int,
        width: int | None,
        height: int | None,
        content: str | None,
        screenshot_key: str | None = None,
    ) -> DocumentPage:
        page = DocumentPage(
            dossier_document_id=document.id,
            page_number=page_number,
            width=width,
            height=height,
            content=content,
            screenshot_key=screenshot_key,
            predictions=[],
            bounding_boxes=[],
        )
        self.db.add(page)
        await self.db.commit()
        # Pas de refresh(page) : redéclencherait un lazy-load de
        # `predictions`/`bounding_boxes` hors contexte async (MissingGreenlet)
        # - voir le commentaire équivalent dans launch(). L'id généré côté
        # client (UUIDMixin.default) est déjà à jour après le commit.
        return page

    def _page_options(self):
        predictions_load = selectinload(DocumentPage.predictions)
        return (
            selectinload(DocumentPage.bounding_boxes),
            predictions_load.selectinload(DocumentPrediction.bounding_boxes),
            _validations_load(predictions_load),
        )

    async def get_page(self, document_id: uuid.UUID, page_id: uuid.UUID) -> DocumentPage | None:
        result = await self.db.execute(
            select(DocumentPage)
            .options(*self._page_options())
            .where(
                DocumentPage.id == page_id,
                DocumentPage.dossier_document_id == document_id,
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_page_by_id(self, page_id: uuid.UUID) -> DocumentPage | None:
        result = await self.db.execute(
            select(DocumentPage)
            .options(*self._page_options())
            .where(DocumentPage.id == page_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def add_bounding_box(
        self,
        page: DocumentPage,
        *,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
    ) -> BoundingBox:
        bbox = BoundingBox(document_page_id=page.id, x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)
        self.db.add(bbox)
        await self.db.commit()
        await self.db.refresh(bbox)
        return bbox

    async def add_prediction(
        self,
        page: DocumentPage,
        *,
        kind: PredictionKind,
        name: str,
        value: str,
        confidence: float | None,
        label_definition_id: uuid.UUID | None = None,
        entity_definition_id: uuid.UUID | None = None,
        page_ids: list[uuid.UUID] | None = None,
        bounding_box_ids: list[uuid.UUID] | None = None,
    ) -> DocumentPrediction:
        """`page` est la page sous laquelle la route de création est
        appelée (POST .../pages/{page_id}/predictions) - une classification
        s'arrête là (l'ensemble ne fait qu'un élément). Une entité peut en
        plus couvrir `page_ids` (d'autres pages) et référencer
        `bounding_box_ids` (déjà créées via add_bounding_box), sur
        potentiellement plusieurs pages."""
        prediction = DocumentPrediction(
            kind=kind,
            name=name,
            value=value,
            confidence=confidence,
            label_definition_id=label_definition_id,
            entity_definition_id=entity_definition_id,
        )
        self.db.add(prediction)
        await self.db.flush()

        all_page_ids = {page.id, *(page_ids or [])}
        await self.db.execute(
            insert(prediction_pages),
            [{"prediction_id": prediction.id, "document_page_id": pid} for pid in all_page_ids],
        )
        if bounding_box_ids:
            await self.db.execute(
                insert(prediction_bounding_boxes),
                [{"prediction_id": prediction.id, "bounding_box_id": bid} for bid in bounding_box_ids],
            )
        await self.db.commit()
        return await self.get_prediction_by_id(prediction.id)

    def _prediction_options(self):
        return (
            selectinload(DocumentPrediction.pages),
            selectinload(DocumentPrediction.bounding_boxes),
            _validations_load(selectinload(DocumentPrediction.analysis_elements), chained=True),
        )

    async def get_prediction(self, page_id: uuid.UUID, prediction_id: uuid.UUID) -> DocumentPrediction | None:
        result = await self.db.execute(
            select(DocumentPrediction)
            .options(*self._prediction_options())
            .where(
                DocumentPrediction.id == prediction_id,
                DocumentPrediction.pages.any(DocumentPage.id == page_id),
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_prediction_by_id(self, prediction_id: uuid.UUID) -> DocumentPrediction | None:
        result = await self.db.execute(
            select(DocumentPrediction)
            .options(*self._prediction_options())
            .where(DocumentPrediction.id == prediction_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def add_prediction_validation(
        self,
        prediction: DocumentPrediction,
        page: DocumentPage,
        *,
        validator_user_id: str,
        status: PredictionValidationStatus,
        corrected_value: str | None,
        bounding_box: dict | None,
    ) -> DocumentPrediction:
        """Enregistre la décision de l'instructeur dans l'analyse de dossier
        (issue #120) : une version d'instructeur de l'élément qui porte la
        prédiction. ``prediction.pages`` doit déjà être chargée (la méthode
        reçoit toujours un objet issu de get_prediction/_by_id). Lève
        AnalysisFrozenError si l'analyse est figée."""
        await record_validation(
            DossierAnalysisRepository(self.db),
            prediction=prediction,
            page=page,
            user_id=validator_user_id,
            status=status,
            corrected_value=corrected_value,
            bounding_box=bounding_box,
        )
        return await self.get_prediction_by_id(prediction.id)

    async def launch(self, dossier: Dossier, analyse: Analyse, actor=None) -> None:
        """Marks the dossier as running and lays down one execution step per
        stage (classification, extraction, one per agent). Actually
        producing a result for each step is the worker's job (issues #4/#5,
        not built yet) - this only records the intent to run."""
        if dossier.status == DossierStatus.EN_COURS:
            return

        now = datetime.now(UTC)
        for existing in list(dossier.execution_steps):
            await self.db.delete(existing)

        steps = [
            ExecutionStep(
                dossier_id=dossier.id,
                kind=ExecutionStepKind.CLASSIFICATION,
                label="Classification documentaire",
                status=ExecutionStepStatus.EN_COURS,
                started_at=now,
                logs=[],
            ),
            ExecutionStep(
                dossier_id=dossier.id,
                kind=ExecutionStepKind.EXTRACTION,
                label="Extraction d'entités nommées",
                status=ExecutionStepStatus.EN_COURS,
                started_at=now,
                logs=[],
            ),
        ]
        for agent in analyse.agents:
            steps.append(
                ExecutionStep(
                    dossier_id=dossier.id,
                    kind=ExecutionStepKind.AGENT,
                    label=agent.name,
                    status=ExecutionStepStatus.EN_COURS,
                    started_at=now,
                    logs=[],
                )
            )

        dossier.execution_steps = steps
        dossier.status = DossierStatus.EN_COURS
        dossier.analyse_version = self._analyse_repository.get_version_label(analyse)
        dossier.started_at = now
        dossier.ended_at = None
        self.events.add(
            dossier.id, DossierEventType.ANALYSIS_STARTED, actor, {"analyse_version": dossier.analyse_version}
        )
        await self.db.commit()
        # Analyse de dossier (#125) : une par exécution (le worker tolère un
        # dossier sans analyse : exécutions déjà en cours avant ce changement).
        analyses = DossierAnalysisRepository(self.db)
        previous = await analyses.get_current(dossier.id)
        await analyses.create_analysis(
            dossier.id,
            analyse_version=dossier.analyse_version,
            started_at=now,
            # Relance incrémentale (#119) : l'analyse précédente sert de référence
            # pour reprendre les unités dont les entrées n'ont pas changé.
            previous_analysis_id=previous.id if previous else None,
        )
        # Pas de refresh(dossier) ici : ça re-déclencherait un lazy-load des
        # nouvelles execution_steps (et de leur relation `logs`, vide mais
        # non chargée) en dehors du contexte async - MissingGreenlet. Les
        # objets Python déjà en mémoire (avec logs=[] posé plus haut) et
        # leurs id générés côté client (UUIDMixin.default) sont à jour après
        # le commit (expire_on_commit=False sur la session).

    async def stop(self, dossier: Dossier, actor=None) -> None:
        if dossier.status != DossierStatus.EN_COURS:
            return
        dossier.status = DossierStatus.ARRETE
        dossier.ended_at = datetime.now(UTC)
        self.events.add(dossier.id, DossierEventType.ANALYSIS_STOPPED, actor)
        await self.db.commit()
        await self.db.refresh(dossier)

    async def delete_dossier(self, dossier: Dossier) -> None:
        """Supprime un dossier et tout ce qui en dépend : fichiers S3 (les
        documents eux-mêmes et les captures de page), puis la ligne Dossier -
        le cascade DB (execution_steps, documents, pages, bounding_boxes,
        conversations...) s'occupe du reste. `dossier` doit venir de get()
        (documents/pages déjà chargés, cf. _base_query).

        S3 est nettoyé avant la ligne DB : si la suppression S3 d'une clé
        échoue silencieusement (S3Connector.delete avale les erreurs), on
        préfère risquer un fichier orphelin sur S3 plutôt qu'une ligne DB
        pointant vers des fichiers déjà supprimés.

        Un dossier encore actif (en_attente/en_cours) ne peut pas être
        supprimé directement : il doit d'abord être arrêté (stop()) - à
        l'appelant (endpoint, tâche de purge) de le faire avant d'appeler
        cette méthode, pas à elle de le faire implicitement."""
        if dossier.status in (DossierStatus.EN_ATTENTE, DossierStatus.EN_COURS):
            raise ValueError(f"Cannot delete dossier {dossier.id}: still {dossier.status} - stop it first")
        for document in dossier.documents:
            await asyncio.to_thread(s3_connector.delete, document.s3_key)
            for page in document.pages:
                if page.screenshot_key:
                    await asyncio.to_thread(s3_connector.delete, page.screenshot_key)
        # Documents générés (#143) : les lignes partent par cascade, pas les fichiers.
        generated = await self.db.execute(
            select(GeneratedDocument.odt_key, GeneratedDocument.pdf_key).where(
                GeneratedDocument.dossier_id == dossier.id
            )
        )
        for odt_key, pdf_key in generated.all():
            for key in (odt_key, pdf_key):
                if key:
                    await asyncio.to_thread(s3_connector.delete, key)
        # Aperçus PDF des brouillons de document (#142) : des objets S3 sans ligne en base.
        await asyncio.to_thread(s3_connector.delete_prefix, f"previews/{dossier.id}/")
        await self.db.delete(dossier)
        await self.db.commit()

    # --- Hash de fichier et résumés (issue #52) ---

    async def set_file_hash(self, document: DossierDocument, file_hash: str) -> None:
        """Dépose le hash SHA-256 d'un document, calculé par le worker
        document_process au moment de l'extraction."""
        document.file_hash = file_hash
        await self.db.commit()

    async def set_document_summary_status(
        self,
        document: DossierDocument,
        status: SummaryStatus,
        error: str | None = None,
    ) -> None:
        document.summary_status = status
        document.summary_error = error
        await self.db.commit()

    async def set_dossier_summary_status(
        self,
        dossier: Dossier,
        status: SummaryStatus,
        error: str | None = None,
    ) -> None:
        dossier.summary_status = status
        dossier.summary_error = error
        await self.db.commit()

    async def add_document_summary(
        self,
        document: DossierDocument,
        *,
        content: str,
        model: str | None = None,
    ) -> DocumentSummary:
        """Insère un nouveau résumé pour un document (append-only) et marque
        le statut comme terminé. La dernière ligne (par created_at) fait foi
        comme résumé courant."""
        summary = DocumentSummary(
            dossier_document_id=document.id,
            content=content,
            model=model,
        )
        self.db.add(summary)
        document.summary_status = SummaryStatus.TERMINE
        document.summary_error = None
        await self.db.commit()
        return summary

    async def add_dossier_summary(
        self,
        dossier: Dossier,
        *,
        content: str,
        model: str | None = None,
    ) -> DossierSummary:
        """Insère un nouveau résumé global pour un dossier (append-only) et
        marque le statut comme terminé."""
        summary = DossierSummary(
            dossier_id=dossier.id,
            content=content,
            model=model,
        )
        self.db.add(summary)
        dossier.summary_status = SummaryStatus.TERMINE
        dossier.summary_error = None
        await self.db.commit()
        return summary

    # --- Suggestions d'analyse (issue #54 : dossier « à ranger ») ---

    async def set_suggestion_status(
        self,
        dossier: Dossier,
        status: SuggestionStatus,
        error: str | None = None,
    ) -> None:
        """Met à jour le statut de génération des suggestions d'analyse."""
        dossier.suggestion_status = status
        # Pas de champ suggestion_error dédié : on loge l'erreur dans
        # summary_error (qui sert déjà de canal d'erreur pour les résumés).
        if error:
            dossier.summary_error = error
        await self.db.commit()

    async def set_suggested_analyses(
        self,
        dossier: Dossier,
        suggestions: list[dict],
    ) -> None:
        """Dépose les suggestions d'analyse générées par le LLM et marque le
        statut comme terminé."""
        dossier.suggested_analyses = suggestions
        dossier.suggestion_status = SuggestionStatus.TERMINE
        await self.db.commit()

    async def assign_analyse(self, dossier: Dossier, analyse: Analyse, actor=None) -> None:
        """Valide le rattachement d'un dossier « à ranger » à une analyse.
        Met à jour analyse_id et analyse_version."""
        dossier.analyse_id = analyse.id
        dossier.analyse_version = self._analyse_repository.get_version_label(analyse)
        # Le dossier reçoit le statut initial de l'analyse qui l'accueille (issue #168).
        dossier.workflow_status_id = self._initial_status_id(analyse)
        dossier.closed_at = None
        # Les colonnes personnalisées de l'analyse qui l'accueille prennent leur valeur par défaut (#173), sans écraser
        # une valeur déjà saisie.
        dossier.custom_values = {**default_values(analyse.custom_fields), **(dossier.custom_values or {})}
        # Un dossier sans échéance prend celle de l'analyse qui l'accueille, si elle en a une par défaut.
        default_due = self._default_due_at(analyse)
        if dossier.due_at is None and default_due is not None:
            dossier.due_at = default_due
            self.events.add(
                dossier.id,
                DossierEventType.DUE_DATE_CHANGED,
                actor,
                {"from": None, "to": default_due.isoformat(), "reason": "default_duration"},
            )
        self.events.add(
            dossier.id,
            DossierEventType.ANALYSE_ASSIGNED,
            actor,
            {"analyse_id": str(analyse.id), "analyse_name": analyse.name},
        )
        await self.db.commit()
