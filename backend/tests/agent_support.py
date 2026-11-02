"""Ce que les tests faisaient par les routes internes du worker (`/api/internal/*`), faits par les services que le
backend appelle lui-même : déposer le message de l'assistant, lire la conversation telle que l'agent la lit…

Les services tournent sur la boucle de l'application (`client.portal`), celle qui possède le moteur de base. Les
réponses ont la forme de celles de `TestClient` (`status_code`, `json()`, `text`) pour que les tests changent peu."""

import json
import uuid
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db import async_session_factory
from app.schemas.dossier import InternalMessageIn, MessageOut
from app.services.chat_conversation import deposit_assistant_message, load_chat_conversation


def _response(status_code: int, body: Any) -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, json=lambda: body, text=json.dumps(body, default=str))


def deposit_message(client: TestClient, conversation_id: str, body: dict) -> SimpleNamespace:
    """Dépose la réponse de l'assistant. 200 et le message ; 422 si le corps est refusé ; 404 sans conversation."""

    async def deposit() -> SimpleNamespace:
        try:
            data = InternalMessageIn.model_validate(body)
        except ValidationError as error:
            return _response(422, {"detail": json.loads(error.json())})
        async with async_session_factory() as db:
            message = await deposit_assistant_message(db, uuid.UUID(conversation_id), data)
            if message is None:
                return _response(404, {"detail": "Conversation introuvable"})
            return _response(200, MessageOut.model_validate(message).model_dump(mode="json"))

    return client.portal.call(deposit)


def internal_conversation(client: TestClient, conversation_id: str) -> dict:
    """La conversation telle que l'agent la lit : historique, modèle, outils à donner au modèle."""

    async def load() -> dict:
        async with async_session_factory() as db:
            conversation = await load_chat_conversation(db, uuid.UUID(conversation_id))
        assert conversation is not None
        return conversation.model_dump(mode="json")

    return client.portal.call(load)
