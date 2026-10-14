from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from contract import example

from millefeuille_ephemeral import EphemeralClient

NOW = "2026-09-30T10:00:00Z"


def analyse_json(analyse_id: str | None = None, persist: bool = False) -> dict[str, Any]:
    """Réponse `EphemeralAnalyseOut` générée depuis l'OpenAPI du backend."""
    return example(
        "EphemeralAnalyseOut", **({"id": analyse_id} if analyse_id else {}), persist=persist, expires_at=None
    )


def run_json(run_id: str | None = None, status: str = "en_cours") -> dict[str, Any]:
    """Réponse `EphemeralRunOut` générée depuis l'OpenAPI du backend."""
    return example(
        "EphemeralRunOut", **({"id": run_id} if run_id else {}), status=status, ttl_hours=24, expires_at=None
    )


@pytest.fixture
def make_client() -> Callable[..., tuple[EphemeralClient, list[httpx.Request]]]:
    def factory(
        handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any
    ) -> tuple[EphemeralClient, list[httpx.Request]]:
        seen: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        kwargs.setdefault("api_token", "ddd_tok")
        kwargs.setdefault("backoff_factor", 0)
        return EphemeralClient("https://api.test", transport=httpx.MockTransport(recording), **kwargs), seen

    return factory


def classification_json(run_id: str | None = None, status: str = "terminé") -> dict[str, Any]:
    """Réponse `EphemeralClassificationOut` générée depuis l'OpenAPI du backend."""
    return example(
        "EphemeralClassificationOut",
        **({"run_id": run_id} if run_id else {}),
        status=status,
        error=None,
        expires_at=None,
    )


def extraction_json(run_id: str | None = None, status: str = "terminé") -> dict[str, Any]:
    """Réponse `EphemeralExtractionOut` générée depuis l'OpenAPI du backend."""
    return example(
        "EphemeralExtractionOut", **({"run_id": run_id} if run_id else {}), status=status, error=None, expires_at=None
    )
