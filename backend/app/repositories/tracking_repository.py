import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import Numeric, Select, String, and_, case, cast, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analyse import Analyse, StatusDefinition
from app.models.app_user import AppUser
from app.models.dossier import Dossier
from app.models.dossier_event import DossierEvent, DossierEventType
from app.repositories.dossier_repository import DossierRepository
from app.services.custom_fields import FieldFilter
from app.services.dossier_access import visible_clause
from app.services.due_date import due_info, today_in_paris
from app.utils.sorting import sort_key

if TYPE_CHECKING:
    from app.core.security.factory import RequestContext

SortKey = Literal[
    "reference", "name", "analyse", "status", "assignee", "due", "created_at", "last_activity_at", "field"
]
StatusCategory = Literal["initial", "progress", "final"]


@dataclass(frozen=True)
class TrackingRow:
    dossier: Dossier
    analyse_name: str
    due: object
    last_activity_at: datetime
    # Définitions des colonnes personnalisées de l'analyse du dossier : elles donnent ses valeurs courantes (#173).
    fields: list[dict]


class TrackingRepository:
    """Lecture du tableau de suivi (issue #173) : filtres, recherche, tri et pagination **côté serveur**."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _last_activity():
        """Dernière action du journal, hors consultations ; à défaut, la création du dossier."""
        latest = (
            select(func.max(DossierEvent.created_at))
            .where(DossierEvent.dossier_id == Dossier.id, DossierEvent.type != DossierEventType.CONSULTED.value)
            .correlate(Dossier)
            .scalar_subquery()
        )
        return func.coalesce(latest, Dossier.created_at)

    @staticmethod
    def _reference():
        """Même formule que `Dossier.reference`, pour pouvoir chercher et trier dessus."""
        year = cast(extract("year", func.timezone("UTC", Dossier.created_at)), String)
        number = cast(Dossier.ref_number, String)
        # `lpad` tronque ce qui dépasse 4 caractères : au-delà de 9 999 dossiers le numéro doit rester entier.
        padded = case((Dossier.ref_number < 10000, func.lpad(number, 4, "0")), else_=number)
        return func.concat("DOS-", func.substr(year, 1, 4), "-", padded)

    @staticmethod
    def _text_of(field_id: str):
        """Valeur du champ en texte (``->>``) ; ``NULL`` si le dossier n'en a pas."""
        return Dossier.custom_values[field_id].as_string()

    @staticmethod
    def _number_of(field_id: str):
        """Valeur du champ en nombre ; ``NULL`` si absente ou si ce n'est pas un nombre (jamais d'erreur de cast)."""
        element = Dossier.custom_values[field_id]
        return case((func.jsonb_typeof(element) == "number", cast(element.as_string(), Numeric)), else_=None)

    @staticmethod
    def _escape_like(text: str) -> str:
        return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _field_condition(self, field_filter: FieldFilter):
        """Condition SQL d'un filtre de colonne personnalisée, selon le type du champ."""
        field_id, field_type = field_filter.field["id"], field_filter.field["type"]
        if field_type in ("number", "amount"):
            expression = self._number_of(field_id)
        elif field_type == "date":
            expression = case((func.jsonb_typeof(Dossier.custom_values[field_id]) == "string", self._text_of(field_id)))
        else:
            text = self._text_of(field_id)
            if field_type == "boolean":
                # Comme l'interface : « non » inclut les dossiers sans valeur.
                return or_(text.is_(None), text == "false") if field_filter.text == "false" else text == "true"
            if field_type == "choice":
                return text == field_filter.text
            return text.ilike(f"%{self._escape_like(field_filter.text or '')}%", escape="\\")
        conditions = []
        if field_filter.minimum is not None:
            conditions.append(expression >= field_filter.minimum)
        if field_filter.maximum is not None:
            conditions.append(expression <= field_filter.maximum)
        return and_(*conditions)

    def _filters(
        self,
        *,
        analyse_ids: Sequence[uuid.UUID],
        status_id: uuid.UUID | None,
        category: StatusCategory | None,
        assignee: str | None,
        due: str | None,
        search: str | None,
        access: str | None,
        field_filters: Sequence[FieldFilter],
        user: "RequestContext | None",
    ) -> list:
        # Le suivi porte sur les dossiers rangés dans une analyse : un dossier « à ranger » n'a ni statut ni seuils.
        filters: list = [Dossier.analyse_id.is_not(None)]
        # Seuls les dossiers visibles de la personne sont listés, et donc comptés et exportés (issue #177).
        if user is not None:
            filters.append(visible_clause(user))
        if analyse_ids:
            filters.append(Dossier.analyse_id.in_(analyse_ids))
        if access:
            filters.append(Dossier.visibility == access)
        if status_id:
            filters.append(Dossier.workflow_status_id == status_id)
        if category == "initial":
            filters.append(StatusDefinition.is_initial.is_(True))
        elif category == "final":
            filters.append(StatusDefinition.is_final.is_(True))
        elif category == "progress":
            filters += [StatusDefinition.id.is_not(None), StatusDefinition.is_initial.is_(False)]
            filters.append(StatusDefinition.is_final.is_(False))
        if assignee == "none":
            filters.append(Dossier.assignee_id.is_(None))
        elif assignee:
            filters.append(Dossier.assignee_id == assignee)
        filters += DossierRepository._due_filters(due)
        if search and search.strip():
            escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            # La recherche porte aussi sur les valeurs des colonnes personnalisées.
            values = func.jsonb_each_text(Dossier.custom_values).table_valued("key", "value")
            in_values = (
                select(1)
                .select_from(values)
                .where(values.c.value.ilike(pattern, escape="\\"))
                .correlate(Dossier)
                .exists()
            )
            filters.append(
                or_(Dossier.name.ilike(pattern, escape="\\"), self._reference().ilike(pattern, escape="\\"), in_values)
            )
        filters += [self._field_condition(f) for f in field_filters]
        return filters

    def _sort_columns(
        self, key: SortKey, descending: bool, last_activity, sort_field: dict | None = None, assignee_rank=None
    ) -> list:
        if key == "field" and sort_field is not None:
            field_id = sort_field["id"]
            expression = (
                self._number_of(field_id)
                if sort_field["type"] in ("number", "amount")
                else func.lower(self._text_of(field_id))
            )
            primary = expression.desc() if descending else expression.asc()
            return [primary.nulls_last(), Dossier.ref_number.desc()]
        columns = {
            "reference": [Dossier.ref_number],
            "name": [func.lower(Dossier.name)],
            "analyse": [func.lower(Analyse.name)],
            "status": [StatusDefinition.position],
            "assignee": [assignee_rank],
            "due": [Dossier.due_at],
            "created_at": [Dossier.created_at],
            "last_activity_at": [last_activity],
        }[key]
        ordered = [column.desc() if descending else column.asc() for column in columns]
        # Les valeurs absentes (sans échéance, non affecté, sans statut) restent en dernier dans les deux sens.
        if key in ("status", "assignee", "due"):
            ordered = [column.nulls_last() for column in ordered]
        return [*ordered, Dossier.ref_number.desc()]

    async def _assignee_rank(self):
        """Rang de chaque personne par nom, à trier en SQL : le nom, chiffré en base, ne s'y trie pas."""
        people = (await self.db.execute(select(AppUser.user_id, AppUser.name))).all()
        if not people:
            return AppUser.user_id
        ordered = sorted(people, key=lambda p: (sort_key(p.name), p.user_id))
        return case({user_id: rank for rank, (user_id, _) in enumerate(ordered)}, value=AppUser.user_id)

    async def list_rows(
        self,
        *,
        page: int,
        page_size: int,
        analyse_ids: Sequence[uuid.UUID] = (),
        status_id: uuid.UUID | None = None,
        category: StatusCategory | None = None,
        assignee: str | None = None,
        due: str | None = None,
        search: str | None = None,
        access: str | None = None,
        field_filters: Sequence[FieldFilter] = (),
        sort: SortKey = "created_at",
        sort_field: dict | None = None,
        descending: bool = True,
        user: "RequestContext | None" = None,
    ) -> tuple[list[TrackingRow], int]:
        last_activity = self._last_activity().label("last_activity_at")
        filters = self._filters(
            analyse_ids=analyse_ids,
            status_id=status_id,
            category=category,
            assignee=assignee,
            due=due,
            search=search,
            access=access,
            field_filters=field_filters,
            user=user,
        )

        def joined(statement: Select) -> Select:
            return (
                statement.join(Analyse, Analyse.id == Dossier.analyse_id)
                .outerjoin(StatusDefinition, StatusDefinition.id == Dossier.workflow_status_id)
                .outerjoin(AppUser, AppUser.user_id == Dossier.assignee_id)
                .where(*filters)
            )

        total = await self.db.scalar(joined(select(func.count()).select_from(Dossier)))
        assignee_rank = await self._assignee_rank() if sort == "assignee" else None
        query = joined(
            select(Dossier, Analyse.name, Analyse.due_thresholds, Analyse.custom_fields, last_activity)
        ).order_by(*self._sort_columns(sort, descending, self._last_activity(), sort_field, assignee_rank))
        result = await self.db.execute(query.limit(page_size).offset((page - 1) * page_size))
        today = today_in_paris()
        rows = [
            TrackingRow(
                dossier=dossier,
                analyse_name=analyse_name,
                due=due_info(dossier.due_at, thresholds, today, closed=dossier.closed_at is not None),
                last_activity_at=activity,
                fields=fields,
            )
            for dossier, analyse_name, thresholds, fields, activity in result.all()
        ]
        return rows, total or 0
