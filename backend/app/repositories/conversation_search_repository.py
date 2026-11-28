"""Recherche plein texte dans les conversations d'une personne (issue #650).

Deux règles de sécurité, appliquées à **chaque** requête : seulement ses conversations (`user_id`, administrateur
compris) et seulement sur les dossiers qu'elle voit encore (`visible_clause`).
"""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.conversation import Conversation, Message
from app.models.dossier import Dossier
from app.schemas.conversation_search import ConversationMatchOut, ConversationSearchResultOut, ExcerptSegmentOut
from app.services.dossier_access import visible_clause
from app.services.full_text import all_terms, headline, search_terms, split_headline, vector


def split_excerpt(value: str) -> list[ExcerptSegmentOut]:
    return [ExcerptSegmentOut(text=text, highlighted=highlighted) for text, highlighted in split_headline(value)]


class ConversationSearchRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(
        self, *, user: RequestContext, query: str, page: int, page_size: int
    ) -> tuple[list[ConversationSearchResultOut], int]:
        terms = search_terms(query)
        if not terms:
            return [], 0
        tsquery = all_terms(terms)
        mine = [Conversation.user_id == user.user_id, visible_clause(user)]

        # Par conversation : le message trouvé le plus récent, et le nombre de messages trouvés.
        ranked = (
            select(
                Message.conversation_id,
                Message.id.label("message_id"),
                Message.role,
                Message.created_at,
                func.row_number()
                .over(partition_by=Message.conversation_id, order_by=(Message.created_at.desc(), Message.id))
                .label("rank"),
                func.count().over(partition_by=Message.conversation_id).label("match_count"),
            )
            .join(Conversation, Message.conversation_id == Conversation.id)
            .join(Dossier, Conversation.dossier_id == Dossier.id)
            .where(*mine, vector(Message.content).op("@@")(tsquery))
            .subquery()
        )
        last_activity = (
            select(func.max(Message.created_at))
            .where(Message.conversation_id == Conversation.id)
            .correlate(Conversation)
            .scalar_subquery()
        )
        date = func.coalesce(ranked.c.created_at, last_activity, Conversation.created_at)
        found = (
            select(
                Conversation.id.label("conversation_id"),
                Dossier.id.label("dossier_id"),
                Dossier.name.label("dossier_name"),
                date.label("date"),
                ranked.c.message_id,
                ranked.c.role,
                ranked.c.match_count,
            )
            .join(Dossier, Conversation.dossier_id == Dossier.id)
            .outerjoin(ranked, (ranked.c.conversation_id == Conversation.id) & (ranked.c.rank == 1))
            .where(*mine, or_(ranked.c.message_id.is_not(None), vector(Dossier.name).op("@@")(tsquery)))
        )

        total = await self.db.scalar(select(func.count()).select_from(found.subquery()))
        rows = (
            await self.db.execute(
                found.order_by(date.desc(), Conversation.id).limit(page_size).offset((page - 1) * page_size)
            )
        ).all()
        excerpts = await self._excerpts([row.message_id for row in rows if row.message_id], tsquery)

        results = [
            ConversationSearchResultOut(
                conversation_id=row.conversation_id,
                dossier_id=row.dossier_id,
                dossier_name=row.dossier_name,
                date=row.date,
                match=ConversationMatchOut(
                    message_id=row.message_id,
                    role=row.role,
                    created_at=row.date,
                    excerpt=excerpts.get(row.message_id, []),
                )
                if row.message_id
                else None,
                match_count=row.match_count or 0,
            )
            for row in rows
        ]
        return results, total or 0

    async def _excerpts(
        self, message_ids: list[uuid.UUID], tsquery: ColumnElement[Any]
    ) -> dict[uuid.UUID, list[ExcerptSegmentOut]]:
        """Les extraits ne sont calculés que pour la page affichée : `ts_headline` est coûteux."""
        if not message_ids:
            return {}
        rows = await self.db.execute(
            select(Message.id, headline(Message.content, tsquery)).where(Message.id.in_(message_ids))
        )
        return {message_id: split_excerpt(excerpt) for message_id, excerpt in rows.all()}
