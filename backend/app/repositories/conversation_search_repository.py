"""Recherche plein texte dans les conversations d'une personne (issue #650).

Deux règles de sécurité, appliquées à **chaque** requête : seulement ses conversations (`user_id`, administrateur
compris) et seulement sur les dossiers qu'elle voit encore (`visible_clause`).
"""

import functools
import re
import uuid
from typing import Any

from sqlalchemy import ColumnElement, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext
from app.models.conversation import Conversation, Message
from app.models.dossier import Dossier
from app.schemas.conversation_search import ConversationMatchOut, ConversationSearchResultOut, ExcerptSegmentOut
from app.services.dossier_access import visible_clause

MAX_TERMS = 10

# Littéraux, jamais des paramètres liés : l'expression doit être identique à celle de l'index `ix_messages_search`.
_FRENCH = literal_column("'french_unaccent'::regconfig")
_SIMPLE = literal_column("'simple_unaccent'::regconfig")
_INDEXED_LENGTH = literal_column("100000")

# Bornes des mots surlignés par `ts_headline` : des caractères de contrôle, absents d'un message.
_START, _STOP = "\x02", "\x03"
_HEADLINE_OPTIONS = f'StartSel="{_START}", StopSel="{_STOP}", MaxWords=18, MinWords=8, MaxFragments=1'


def search_terms(query: str) -> list[str]:
    """Les mots cherchés. Ne gardent que lettres et chiffres : aucun opérateur de `to_tsquery` ne passe."""
    return re.findall(r"[^\W_]+", query)[:MAX_TERMS]


def _vector(column: ColumnElement[str]) -> ColumnElement[Any]:
    text = func.left(column, _INDEXED_LENGTH)
    return func.tsvector_concat(func.to_tsvector(_FRENCH, text), func.to_tsvector(_SIMPLE, text))


def _tsquery(terms: list[str]) -> ColumnElement[Any]:
    """Tous les mots, chacun sous une forme proche (pluriel, accord) **ou** comme début de mot."""
    each = [func.tsquery_or(func.to_tsquery(_FRENCH, term), func.to_tsquery(_SIMPLE, f"{term}:*")) for term in terms]
    return functools.reduce(func.tsquery_and, each)


def split_excerpt(headline: str) -> list[ExcerptSegmentOut]:
    segments: list[ExcerptSegmentOut] = []
    for index, part in enumerate(re.split(f"[{_START}{_STOP}]", " ".join(headline.split()))):
        if part:
            # Les bornes alternent : les morceaux de rang impair sont entre un début et une fin.
            segments.append(ExcerptSegmentOut(text=part, highlighted=index % 2 == 1))
    return segments


class ConversationSearchRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(
        self, *, user: RequestContext, query: str, page: int, page_size: int
    ) -> tuple[list[ConversationSearchResultOut], int]:
        terms = search_terms(query)
        if not terms:
            return [], 0
        tsquery = _tsquery(terms)
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
            .where(*mine, _vector(Message.content).op("@@")(tsquery))
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
            .where(*mine, or_(ranked.c.message_id.is_not(None), _vector(Dossier.name).op("@@")(tsquery)))
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
        # Sans les marques de mise en forme d'une réponse, illisibles dans un extrait.
        plain = func.regexp_replace(func.left(Message.content, _INDEXED_LENGTH), r"[*`#|]+", "", "g")
        rows = await self.db.execute(
            select(Message.id, func.ts_headline(_FRENCH, plain, tsquery, _HEADLINE_OPTIONS)).where(
                Message.id.in_(message_ids)
            )
        )
        return {message_id: split_excerpt(headline) for message_id, headline in rows.all()}
