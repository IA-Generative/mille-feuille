import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.connectors import s3_connector
from app.core.security.share_token import generate_token, hash_token
from app.models.analyse import (
    Agent,
    Analyse,
    EntityDefinition,
    FieldVersion,
    LabelDefinition,
    StatusDefinition,
    VersionedField,
)
from app.models.analyse_share import AnalyseShare, AnalyseShareKind
from app.models.document_template import DocumentTemplate, DocumentTemplateVersion
from app.models.dossier import Dossier
from app.models.dossier_event import DossierEventType
from app.repositories.dossier_event_repository import DossierEventRepository
from app.services.due_date import normalize_thresholds
from app.services.tools.ids import unique

if TYPE_CHECKING:
    from app.schemas.analyse import AgentOut, AnalyseOut, CustomFieldsUpdate, DueSettingsIn, StatusDefinitionIn


# Statuts donnés à toute nouvelle analyse (nom, couleur, initial, final) : un point de départ que
# l'administrateur adapte ensuite (issue #168).
DEFAULT_STATUSES = [
    ("À instruire", "#6a6af4", True, False),
    ("En instruction", "#0063cb", False, False),
    ("Terminé", "#18753c", False, True),
]


class StatusValidationError(ValueError):
    """La liste de statuts proposée ne respecte pas les règles (message destiné à l'utilisateur)."""


class StatusInUseError(Exception):
    """Des statuts supprimés sont encore utilisés par des dossiers sans statut de remplacement.
    ``in_use`` : [{"id", "name", "dossier_count"}]."""

    def __init__(self, in_use: list[dict]) -> None:
        super().__init__("Des statuts supprimés sont encore utilisés par des dossiers.")
        self.in_use = in_use


def _closed_at_for(is_final: bool):
    """Valeur de Dossier.closed_at quand un dossier entre dans un statut : posée à la première clôture
    (conservée s'il passe d'un statut final à un autre), effacée dans un statut non final."""
    return func.coalesce(Dossier.closed_at, func.now()) if is_final else None


def _status_snapshot(statuses) -> list[dict]:
    return [
        {
            "id": str(status.id),
            "name": status.name,
            "color": status.color,
            "position": status.position,
            "is_initial": status.is_initial,
            "is_final": status.is_final,
        }
        for status in statuses
    ]


class AnalyseRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _base_query(self):
        # populate_existing: sans ça, un get() qui retombe sur un objet déjà
        # dans l'identity map de la session (ex: get() juste après create(),
        # ou plusieurs update_* enchaînés dans la même requête) renverrait ses
        # relations telles que laissées par le dernier accès/refresh, pas
        # rechargées depuis la DB - même raison que le commentaire équivalent
        # dans DossierRepository._base_query.
        return (
            select(Analyse)
            .options(
                selectinload(Analyse.labels),
                selectinload(Analyse.entities),
                selectinload(Analyse.statuses),
                selectinload(Analyse.agents),
                selectinload(Analyse.field_versions),
                selectinload(Analyse.shares),
            )
            .execution_options(populate_existing=True)
        )

    async def list_all(self) -> Sequence[Analyse]:
        result = await self.db.execute(self._base_query().order_by(Analyse.created_at.desc()))
        return result.scalars().all()

    async def list_paginated(self, *, page: int, page_size: int, q: str | None = None) -> tuple[Sequence[Analyse], int]:
        # Recherche par nom, insensible à la casse - utilisée par le tool
        # search_analyses de l'agent helper (issue #50) en plus de la liste
        # simple côté UI.
        filters = [Analyse.name.ilike(f"%{q}%")] if q else []
        total = await self.db.scalar(select(func.count()).select_from(Analyse).where(*filters))
        result = await self.db.execute(
            self._base_query()
            .where(*filters)
            .order_by(Analyse.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return result.scalars().all(), total or 0

    async def list_shares_paginated(
        self, *, analyse_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[Sequence[AnalyseShare], int]:
        count_query = select(func.count()).select_from(AnalyseShare).where(AnalyseShare.analyse_id == analyse_id)
        total = await self.db.scalar(count_query)
        result = await self.db.execute(
            select(AnalyseShare)
            .where(AnalyseShare.analyse_id == analyse_id)
            .order_by(AnalyseShare.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return result.scalars().all(), total or 0

    async def get(self, analyse_id: uuid.UUID) -> Analyse | None:
        result = await self.db.execute(self._base_query().where(Analyse.id == analyse_id))
        return result.scalar_one_or_none()

    async def create(self, *, name: str, description: str, multi_label: bool = False) -> Analyse:
        analyse = Analyse(name=name, description=description, multi_label=multi_label)
        analyse.statuses = [
            StatusDefinition(name=status_name, color=color, position=position, is_initial=initial, is_final=final)
            for position, (status_name, color, initial, final) in enumerate(DEFAULT_STATUSES)
        ]
        self.db.add(analyse)
        await self.db.commit()
        await self.db.refresh(analyse)
        return analyse

    async def delete(self, analyse: Analyse) -> None:
        """Lève sqlalchemy.exc.IntegrityError si un Dossier référence encore
        cette analyse (FK Dossier.analyse_id, ondelete="RESTRICT") - à
        l'appelant de la traduire en réponse HTTP (409).

        Les modèles de document de l'analyse partent avec elle (cascade) ; leurs fichiers S3, qui ne
        sont pas des lignes, sont supprimés ensuite (issue #139)."""
        keys = (
            await self.db.execute(
                select(DocumentTemplateVersion.file_key)
                .join(DocumentTemplate, DocumentTemplate.id == DocumentTemplateVersion.template_id)
                .where(DocumentTemplate.analyse_id == analyse.id)
            )
        ).scalars()
        template_files = set(keys)
        await self.db.delete(analyse)
        await self.db.commit()
        for key in template_files:
            await asyncio.to_thread(s3_connector.delete, key)

    # --- Versioning: a single mechanism reused for every editable field ---

    def _record_version(
        self,
        analyse: Analyse,
        field: VersionedField,
        content,
        agent: Agent | None = None,
    ) -> None:
        self.db.add(
            FieldVersion(
                analyse_id=analyse.id,
                agent_id=agent.id if agent else None,
                field=field,
                content=content,
            )
        )

    def field_versions(self, analyse: Analyse, field: VersionedField, agent_id: uuid.UUID | None = None):
        return [
            version for version in analyse.field_versions if version.field == field and version.agent_id == agent_id
        ]

    async def restore_field_version(
        self,
        analyse: Analyse,
        field: VersionedField,
        version_id: uuid.UUID,
        agent: Agent | None = None,
    ) -> None:
        agent_id = agent.id if agent else None
        version = next(
            (v for v in analyse.field_versions if v.id == version_id and v.field == field and v.agent_id == agent_id),
            None,
        )
        if version is None:
            return
        await self._apply_field(analyse, field, version.content, agent)

    async def _apply_field(self, analyse: Analyse, field: VersionedField, content, agent: Agent | None) -> None:
        if field == VersionedField.CLASSIFICATION_PROMPT:
            await self.update_classification_prompt(analyse, content)
        elif field == VersionedField.CLASSIFICATION_LABELS:
            await self.update_classification_labels(analyse, [LabelDefinition(**item) for item in content])
        elif field == VersionedField.EXTRACTION_PROMPT:
            await self.update_extraction_prompt(analyse, content)
        elif field == VersionedField.EXTRACTION_ENTITIES:
            await self.update_extraction_entities(analyse, [EntityDefinition(**item) for item in content])
        elif field == VersionedField.AGENT_PROMPT and agent:
            await self.update_agent_prompt(analyse, agent, content)
        elif field == VersionedField.AGENT_TOOLS and agent:
            await self.update_agent_tools(analyse, agent, list(content))
        elif field == VersionedField.AGENT_OUTPUT and agent:
            await self.update_agent_output(analyse, agent, content)
        elif field == VersionedField.AGENT_MODEL and agent:
            await self.update_agent_model(analyse, agent, content)

    # --- Classification ---

    async def update_classification_prompt(self, analyse: Analyse, prompt: str) -> None:
        if analyse.classification_prompt == prompt:
            return
        self._record_version(analyse, VersionedField.CLASSIFICATION_PROMPT, analyse.classification_prompt)
        analyse.classification_prompt = prompt
        await self.db.commit()
        await self.db.refresh(analyse)

    async def update_classification_labels(self, analyse: Analyse, labels: list[LabelDefinition]) -> None:
        snapshot = [{"name": label.name, "definition": label.definition} for label in analyse.labels]
        self._record_version(analyse, VersionedField.CLASSIFICATION_LABELS, snapshot)
        for existing in list(analyse.labels):
            await self.db.delete(existing)
        analyse.labels = [
            LabelDefinition(analyse_id=analyse.id, name=lbl.name, definition=lbl.definition) for lbl in labels
        ]
        await self.db.commit()
        await self.db.refresh(analyse)

    # --- Extraction ---

    async def update_extraction_prompt(self, analyse: Analyse, prompt: str) -> None:
        if analyse.extraction_prompt == prompt:
            return
        self._record_version(analyse, VersionedField.EXTRACTION_PROMPT, analyse.extraction_prompt)
        analyse.extraction_prompt = prompt
        await self.db.commit()
        await self.db.refresh(analyse)

    async def update_extraction_entities(self, analyse: Analyse, entities: list[EntityDefinition]) -> None:
        snapshot = [
            {"name": entity.name, "definition": entity.definition, "type": entity.type} for entity in analyse.entities
        ]
        self._record_version(analyse, VersionedField.EXTRACTION_ENTITIES, snapshot)
        for existing in list(analyse.entities):
            await self.db.delete(existing)
        analyse.entities = [
            EntityDefinition(
                analyse_id=analyse.id,
                name=ent.name,
                definition=ent.definition,
                type=ent.type,
            )
            for ent in entities
        ]
        await self.db.commit()
        await self.db.refresh(analyse)

    # --- Statuts de dossier (issue #168) ---

    @staticmethod
    def initial_status(analyse: Analyse) -> StatusDefinition | None:
        return next((status for status in analyse.statuses if status.is_initial), None)

    @staticmethod
    def _validate_statuses(
        items: "list[StatusDefinitionIn]", existing: dict[uuid.UUID, StatusDefinition], allow_new_ids: bool
    ) -> None:
        if not items:
            raise StatusValidationError("Une analyse doit avoir au moins un statut.")
        names = [item.name.casefold() for item in items]
        if len(set(names)) != len(names):
            raise StatusValidationError("Deux statuts ne peuvent pas porter le même nom.")
        ids = [item.id for item in items if item.id is not None]
        if len(set(ids)) != len(ids):
            raise StatusValidationError("Un statut apparaît deux fois dans la liste.")
        if not allow_new_ids and any(item_id not in existing for item_id in ids):
            raise StatusValidationError("Statut inconnu : il n'appartient pas à cette analyse.")
        if sum(item.is_initial for item in items) != 1:
            raise StatusValidationError("Une analyse doit avoir exactement un statut initial.")
        if any(item.is_initial and item.is_final for item in items):
            raise StatusValidationError("Un statut ne peut pas être à la fois initial et final.")

    async def update_statuses(
        self,
        analyse: Analyse,
        items: "list[StatusDefinitionIn]",
        replacements: dict[uuid.UUID, uuid.UUID] | None = None,
        *,
        allow_new_ids: bool = False,
        actor=None,
    ) -> None:
        """Remplace la liste des statuts de l'analyse en conservant l'identité de ceux qui ont un ``id``.

        - un statut supprimé encore utilisé par des dossiers exige un statut de remplacement
          (``replacements``), sinon ``StatusInUseError`` ;
        - les dossiers reprennent le statut de remplacement, et ``closed_at`` suit le caractère final ;
        - changer le caractère final d'un statut recalcule ``closed_at`` de ses dossiers ;
        - l'état précédent est conservé dans l'historique (restaurable) ;
        - ``allow_new_ids`` : autorise un ``id`` inconnu (restauration d'une version, qui recrée un statut supprimé).
        """
        replacements = replacements or {}
        existing = {status.id: status for status in analyse.statuses}
        self._validate_statuses(items, existing, allow_new_ids)

        kept_ids = {item.id for item in items if item.id in existing}
        removed = [status for status in analyse.statuses if status.id not in kept_ids]

        # Statuts supprimés encore utilisés : chacun doit avoir un remplaçant parmi les statuts conservés.
        replacement_of: dict[uuid.UUID, uuid.UUID] = {}
        if removed:
            counts = dict(
                (
                    await self.db.execute(
                        select(Dossier.workflow_status_id, func.count())
                        .where(Dossier.workflow_status_id.in_([status.id for status in removed]))
                        .group_by(Dossier.workflow_status_id)
                    )
                ).all()
            )
            in_use = [
                {"id": str(status.id), "name": status.name, "dossier_count": counts[status.id]}
                for status in removed
                if counts.get(status.id)
            ]
            missing = [entry for entry in in_use if replacements.get(uuid.UUID(entry["id"])) not in kept_ids]
            if missing:
                raise StatusInUseError(missing)
            replacement_of = {uuid.UUID(entry["id"]): replacements[uuid.UUID(entry["id"])] for entry in in_use}

        new_state = [
            {
                "id": str(item.id) if item.id in existing else None,
                "name": item.name,
                "color": item.color,
                "position": position,
                "is_initial": item.is_initial,
                "is_final": item.is_final,
            }
            for position, item in enumerate(items)
        ]
        current = _status_snapshot(analyse.statuses)
        if not removed and new_state == current:
            return  # rien ne change : pas de version inutile

        self._record_version(analyse, VersionedField.STATUSES, current)

        events = DossierEventRepository(self.db)
        names = {status.id: status.name for status in analyse.statuses}

        # Dossiers des statuts supprimés : ils reprennent le statut de remplacement.
        for old_id, new_id in replacement_of.items():
            new_item = next(item for item in items if item.id == new_id)
            moved = (
                await self.db.execute(select(Dossier.id, Dossier.closed_at).where(Dossier.workflow_status_id == old_id))
            ).all()
            for dossier_id, closed_at in moved:
                payload = {
                    "from": {"id": str(old_id), "name": names[old_id]},
                    "to": {"id": str(new_id), "name": new_item.name},
                    "reason": "status_removed",
                }
                events.add(dossier_id, DossierEventType.STATUS_CHANGED, actor, payload)
                if new_item.is_final and closed_at is None:
                    events.add(
                        dossier_id,
                        DossierEventType.CLOSED,
                        actor,
                        {"status": payload["to"], "reason": "status_removed"},
                    )
                elif not new_item.is_final and closed_at is not None:
                    events.add(
                        dossier_id,
                        DossierEventType.REOPENED,
                        actor,
                        {"status": payload["to"], "reason": "status_removed"},
                    )
            await self.db.execute(
                update(Dossier)
                .where(Dossier.workflow_status_id == old_id)
                .values(workflow_status_id=new_id, closed_at=_closed_at_for(new_item.is_final))
            )

        for position, item in enumerate(items):
            status = existing.get(item.id) if item.id is not None else None
            if status is None:
                status = StatusDefinition(id=item.id, analyse_id=analyse.id)
                self.db.add(status)
            elif status.is_final != item.is_final:
                # Un statut qui devient final (ou cesse de l'être) clôt (ou rouvre) ses dossiers.
                affected = (
                    await self.db.execute(
                        select(Dossier.id, Dossier.closed_at).where(Dossier.workflow_status_id == status.id)
                    )
                ).all()
                for dossier_id, closed_at in affected:
                    if item.is_final and closed_at is None:
                        kind = DossierEventType.CLOSED
                    elif not item.is_final and closed_at is not None:
                        kind = DossierEventType.REOPENED
                    else:
                        continue
                    events.add(
                        dossier_id,
                        kind,
                        actor,
                        {"status": {"id": str(status.id), "name": item.name}, "reason": "status_flag_changed"},
                    )
                await self.db.execute(
                    update(Dossier)
                    .where(Dossier.workflow_status_id == status.id)
                    .values(closed_at=_closed_at_for(item.is_final))
                )
            status.name = item.name
            status.color = item.color
            status.position = position
            status.is_initial = item.is_initial
            status.is_final = item.is_final

        for status in removed:
            await self.db.delete(status)
        await self.db.commit()
        await self.db.refresh(analyse)

    async def restore_statuses_version(
        self,
        analyse: Analyse,
        version_id: uuid.UUID,
        replacements: dict[uuid.UUID, uuid.UUID] | None = None,
        actor=None,
    ) -> bool:
        """Restaure une version antérieure de la liste des statuts (l'état courant devient lui-même une
        version). Renvoie False si la version n'existe pas pour cette analyse."""
        from app.schemas.analyse import StatusDefinitionIn

        version = next(
            (v for v in analyse.field_versions if v.id == version_id and v.field == VersionedField.STATUSES), None
        )
        if version is None:
            return False
        items = [
            StatusDefinitionIn(
                id=uuid.UUID(entry["id"]),
                name=entry["name"],
                color=entry["color"],
                is_initial=entry["is_initial"],
                is_final=entry["is_final"],
            )
            for entry in sorted(version.content, key=lambda entry: entry["position"])
        ]
        await self.update_statuses(analyse, items, replacements, allow_new_ids=True, actor=actor)
        return True

    # --- Échéance des dossiers (issue #172) ---

    @staticmethod
    def due_settings_snapshot(analyse: Analyse) -> dict:
        """Durée par défaut et seuils de couleur, tels qu'ils sont conservés dans une version."""
        return {"default_due_days": analyse.default_due_days, "thresholds": analyse.due_thresholds}

    async def update_due_settings(self, analyse: Analyse, settings: "DueSettingsIn") -> None:
        """Remplace la durée par défaut et les seuils de couleur ; l'état précédent est conservé dans
        l'historique (restaurable). Rien ne change pour les dossiers : leur niveau est calculé à la lecture."""
        new_state = {
            "default_due_days": settings.default_due_days,
            "thresholds": normalize_thresholds(settings.thresholds.model_dump()),
        }
        if new_state == self.due_settings_snapshot(analyse):
            return  # rien ne change : pas de version inutile
        self._record_version(analyse, VersionedField.DUE_SETTINGS, self.due_settings_snapshot(analyse))
        analyse.default_due_days = new_state["default_due_days"]
        analyse.due_thresholds = new_state["thresholds"]
        await self.db.commit()
        await self.db.refresh(analyse)

    async def restore_due_settings_version(self, analyse: Analyse, version_id: uuid.UUID) -> bool:
        """Restaure une version antérieure ; l'état courant devient lui-même une version. False si inconnue."""
        from app.schemas.analyse import DueSettingsIn

        version = next(
            (v for v in analyse.field_versions if v.id == version_id and v.field == VersionedField.DUE_SETTINGS),
            None,
        )
        if version is None:
            return False
        await self.update_due_settings(analyse, DueSettingsIn.model_validate(version.content))
        return True

    # --- Colonnes personnalisées du suivi (issue #173) ---

    @staticmethod
    def custom_fields_snapshot(analyse: Analyse) -> list[dict]:
        """Définitions des colonnes personnalisées, telles qu'elles sont conservées dans une version."""
        return [dict(field) for field in analyse.custom_fields]

    async def update_custom_fields(self, analyse: Analyse, update_in: "CustomFieldsUpdate") -> list[str]:
        """Remplace les définitions des colonnes personnalisées ; l'état précédent est conservé dans l'historique
        (restaurable). Renvoie les identifiants des champs dont les **valeurs ont été supprimées** des dossiers :
        - un champ dont le **type change** perd ses valeurs (elles n'auraient plus de sens) ;
        - un champ **supprimé** garde ses valeurs (récupérables en le restaurant) sauf si ``purge_removed``."""
        existing = {field["id"]: field for field in analyse.custom_fields}
        fresh: list[dict] = []
        for field_in in update_in.fields:
            data = field_in.model_dump()
            data["id"] = data["id"] or f"f_{uuid.uuid4().hex[:10]}"
            fresh.append(data)

        removed = [field_id for field_id in existing if field_id not in {f["id"] for f in fresh}]
        retyped = [f["id"] for f in fresh if f["id"] in existing and existing[f["id"]]["type"] != f["type"]]
        to_purge = [*retyped, *(removed if update_in.purge_removed else [])]
        if fresh == self.custom_fields_snapshot(analyse) and not to_purge:
            return []  # rien ne change : pas de version inutile

        if fresh != self.custom_fields_snapshot(analyse):
            self._record_version(analyse, VersionedField.CUSTOM_FIELDS, self.custom_fields_snapshot(analyse))
            analyse.custom_fields = fresh
        if to_purge:
            await self.db.execute(
                text(
                    "UPDATE dossiers SET custom_values = custom_values - CAST(:keys AS text[]) WHERE analyse_id = :id"
                ),
                {"keys": to_purge, "id": analyse.id},
            )
        await self.db.commit()
        await self.db.refresh(analyse)
        return to_purge

    async def restore_custom_fields_version(self, analyse: Analyse, version_id: uuid.UUID) -> bool:
        """Restaure une version antérieure ; l'état courant devient lui-même une version. False si inconnue."""
        from app.schemas.analyse import CustomFieldIn, CustomFieldsUpdate

        version = next(
            (v for v in analyse.field_versions if v.id == version_id and v.field == VersionedField.CUSTOM_FIELDS),
            None,
        )
        if version is None:
            return False
        await self.update_custom_fields(
            analyse, CustomFieldsUpdate(fields=[CustomFieldIn.model_validate(item) for item in version.content])
        )
        return True

    # --- Collections de la base de connaissances (issue #358) ---

    async def update_knowledge_collections(self, analyse: Analyse, collections: list[dict]) -> None:
        """Remplace la liste ; l'état précédent est conservé dans l'historique (restaurable). Rien ne change : pas de
        version inutile."""
        if collections == analyse.knowledge_collections:
            return
        self._record_version(analyse, VersionedField.KNOWLEDGE_COLLECTIONS, list(analyse.knowledge_collections))
        analyse.knowledge_collections = collections
        await self.db.commit()
        await self.db.refresh(analyse)

    def knowledge_collections_version(self, analyse: Analyse, version_id: uuid.UUID):
        return next(
            (v for v in self.field_versions(analyse, VersionedField.KNOWLEDGE_COLLECTIONS) if v.id == version_id), None
        )

    # --- Réglages de recherche (découpage des pages et modèle d'embeddings) ---

    async def update_search_settings(self, analyse: Analyse, settings: dict) -> None:
        """Remplace les réglages ; l'état précédent est conservé dans l'historique (restaurable). Rien ne change : pas
        de version inutile."""
        if settings == analyse.search_settings:
            return
        self._record_version(analyse, VersionedField.SEARCH_SETTINGS, dict(analyse.search_settings))
        analyse.search_settings = settings
        await self.db.commit()
        await self.db.refresh(analyse)

    def search_settings_version(self, analyse: Analyse, version_id: uuid.UUID):
        return next(
            (v for v in self.field_versions(analyse, VersionedField.SEARCH_SETTINGS) if v.id == version_id), None
        )

    # --- Réglages de la lecture des documents scannés (modèle qui décrit les images) ---

    async def update_ocr_settings(self, analyse: Analyse, settings: dict) -> None:
        """Remplace les réglages ; l'état précédent est conservé dans l'historique (restaurable). Rien ne change : pas
        de version inutile."""
        if settings == analyse.ocr_settings:
            return
        self._record_version(analyse, VersionedField.OCR_SETTINGS, dict(analyse.ocr_settings))
        analyse.ocr_settings = settings
        await self.db.commit()
        await self.db.refresh(analyse)

    def ocr_settings_version(self, analyse: Analyse, version_id: uuid.UUID):
        return next((v for v in self.field_versions(analyse, VersionedField.OCR_SETTINGS) if v.id == version_id), None)

    # --- Agents ---

    async def add_agent(
        self,
        analyse: Analyse,
        *,
        name: str,
        prompt: str,
        tools: list[str],
        output: bool,
        model: str | None = None,
    ) -> Agent:
        agent = Agent(
            analyse_id=analyse.id,
            name=name,
            prompt=prompt,
            tools=unique(tools),
            output=output,
            model=model,
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(analyse)
        return agent

    def get_agent(self, analyse: Analyse, agent_id: uuid.UUID) -> Agent | None:
        return next((a for a in analyse.agents if a.id == agent_id), None)

    async def update_agent_prompt(self, analyse: Analyse, agent: Agent, prompt: str) -> None:
        if agent.prompt == prompt:
            return
        self._record_version(analyse, VersionedField.AGENT_PROMPT, agent.prompt, agent)
        agent.prompt = prompt
        await self.db.commit()
        await self.db.refresh(analyse)

    async def update_agent_tools(self, analyse: Analyse, agent: Agent, tools: list[str]) -> None:
        new_values = unique(tools)
        if sorted(agent.tools) == sorted(new_values):
            return
        self._record_version(analyse, VersionedField.AGENT_TOOLS, agent.tools, agent)
        agent.tools = new_values
        await self.db.commit()
        await self.db.refresh(analyse)

    async def update_agent_output(self, analyse: Analyse, agent: Agent, output: bool) -> None:
        if agent.output == output:
            return
        self._record_version(analyse, VersionedField.AGENT_OUTPUT, agent.output, agent)
        agent.output = output
        await self.db.commit()
        await self.db.refresh(analyse)

    async def update_agent_model(self, analyse: Analyse, agent: Agent, model: str | None) -> None:
        if agent.model == model:
            return
        self._record_version(analyse, VersionedField.AGENT_MODEL, agent.model, agent)
        agent.model = model
        await self.db.commit()
        await self.db.refresh(analyse)

    # --- Version-derived analyse version label ---

    def get_version_label(self, analyse: Analyse) -> str:
        """v1 at the start, +1 per saved change - every FieldVersion row,
        prompt/labels/entities/agents alike, counts once."""
        return f"v{len(analyse.field_versions) + 1}"

    # --- Serialization: the ORM shape (flat field_versions) doesn't match the
    # API's nested shape (promptVersions/labelsVersions per field), so it's
    # built by hand here rather than relying on Pydantic's from_attributes. ---

    def to_agent_schema(self, analyse: Analyse, agent: Agent) -> "AgentOut":
        from app.schemas.analyse import (
            AgentOut,
            Version,
        )  # noqa: F401

        return AgentOut(
            id=agent.id,
            name=agent.name,
            prompt=agent.prompt,
            prompt_versions=[
                Version(id=v.id, content=v.content, created_at=v.created_at)
                for v in self.field_versions(analyse, VersionedField.AGENT_PROMPT, agent.id)
            ],
            tools=list(agent.tools),
            tools_versions=[
                Version(
                    id=v.id,
                    content=list(v.content),
                    created_at=v.created_at,
                )
                for v in self.field_versions(analyse, VersionedField.AGENT_TOOLS, agent.id)
            ],
            output=agent.output,
            output_versions=[
                Version(id=v.id, content=v.content, created_at=v.created_at)
                for v in self.field_versions(analyse, VersionedField.AGENT_OUTPUT, agent.id)
            ],
            model=agent.model,
            model_versions=[
                Version(id=v.id, content=v.content, created_at=v.created_at)
                for v in self.field_versions(analyse, VersionedField.AGENT_MODEL, agent.id)
            ],
        )

    def to_schema(self, analyse: Analyse) -> "AnalyseOut":
        from app.schemas.analyse import (
            AnalyseOut,
            ClassificationOut,
            CustomFieldOut,
            DueSettingsOut,
            EntityDefinitionOut,
            ExtractionOut,
            LabelDefinitionOut,
            StatusDefinitionOut,
            Version,
        )

        classification = ClassificationOut(
            prompt=analyse.classification_prompt,
            prompt_versions=[
                Version(id=v.id, content=v.content, created_at=v.created_at)
                for v in self.field_versions(analyse, VersionedField.CLASSIFICATION_PROMPT)
            ],
            labels=[LabelDefinitionOut.model_validate(label) for label in analyse.labels],
            labels_versions=[
                Version(
                    id=v.id,
                    content=[LabelDefinitionOut(id=uuid.uuid4(), **item) for item in v.content],
                    created_at=v.created_at,
                )
                for v in self.field_versions(analyse, VersionedField.CLASSIFICATION_LABELS)
            ],
        )
        extraction = ExtractionOut(
            prompt=analyse.extraction_prompt,
            prompt_versions=[
                Version(id=v.id, content=v.content, created_at=v.created_at)
                for v in self.field_versions(analyse, VersionedField.EXTRACTION_PROMPT)
            ],
            entities=[EntityDefinitionOut.model_validate(entity) for entity in analyse.entities],
            entities_versions=[
                Version(
                    id=v.id,
                    content=[EntityDefinitionOut(id=uuid.uuid4(), **item) for item in v.content],
                    created_at=v.created_at,
                )
                for v in self.field_versions(analyse, VersionedField.EXTRACTION_ENTITIES)
            ],
        )
        return AnalyseOut(
            id=analyse.id,
            name=analyse.name,
            description=analyse.description,
            created_at=analyse.created_at,
            version=self.get_version_label(analyse),
            classification=classification,
            extraction=extraction,
            custom_fields=[CustomFieldOut.model_validate(field) for field in analyse.custom_fields],
            custom_fields_versions=[
                Version(
                    id=v.id,
                    content=[CustomFieldOut.model_validate(item) for item in v.content],
                    created_at=v.created_at,
                )
                for v in self.field_versions(analyse, VersionedField.CUSTOM_FIELDS)
            ],
            due_settings=DueSettingsOut.model_validate(self.due_settings_snapshot(analyse)),
            due_settings_versions=[
                Version(id=v.id, content=DueSettingsOut.model_validate(v.content), created_at=v.created_at)
                for v in self.field_versions(analyse, VersionedField.DUE_SETTINGS)
            ],
            statuses=[StatusDefinitionOut.model_validate(status) for status in analyse.statuses],
            statuses_versions=[
                Version(
                    id=v.id,
                    content=[StatusDefinitionOut(**item) for item in v.content],
                    created_at=v.created_at,
                )
                for v in self.field_versions(analyse, VersionedField.STATUSES)
            ],
            agents=[self.to_agent_schema(analyse, agent) for agent in analyse.agents],
        )

    # --- Partage ---

    async def create_email_share(
        self, analyse: Analyse, *, email: str, expires_in_hours: int, created_by: str
    ) -> tuple[AnalyseShare, str]:
        token = generate_token()
        share = AnalyseShare(
            analyse_id=analyse.id,
            kind=AnalyseShareKind.EMAIL,
            email=email,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(hours=expires_in_hours),
            created_by=created_by,
        )
        self.db.add(share)
        await self.db.commit()
        await self.db.refresh(share)
        return share, token

    async def create_group_share(self, analyse: Analyse, *, keycloak_group: str, created_by: str) -> AnalyseShare:
        share = AnalyseShare(
            analyse_id=analyse.id,
            kind=AnalyseShareKind.KEYCLOAK_GROUP,
            keycloak_group=keycloak_group,
            created_by=created_by,
        )
        self.db.add(share)
        await self.db.commit()
        await self.db.refresh(share)
        return share

    async def revoke_share(self, share: AnalyseShare) -> None:
        await self.db.delete(share)
        await self.db.commit()

    async def get_share_by_id(self, analyse_id: uuid.UUID, share_id: uuid.UUID) -> AnalyseShare | None:
        result = await self.db.execute(
            select(AnalyseShare).where(AnalyseShare.id == share_id, AnalyseShare.analyse_id == analyse_id)
        )
        return result.scalar_one_or_none()

    async def get_by_share_token(self, token: str) -> Analyse | None:
        result = await self.db.execute(select(AnalyseShare).where(AnalyseShare.token_hash == hash_token(token)))
        share = result.scalar_one_or_none()
        if share is None or (share.expires_at and share.expires_at < datetime.now(UTC)):
            return None
        return await self.get(share.analyse_id)
