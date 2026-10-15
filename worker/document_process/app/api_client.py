import httpx

from app.config import settings


def get_client() -> httpx.Client:
    """Client HTTP authentifié vers le BFF, pour tous les appels à
    /api/internal/* (logs d'exécution, pages/prédictions extraites d'un
    document...). Le jeton (voir app.core.security.internal.verify_app_token
    côté backend) est soit le secret de bootstrap fixe (dev local, docker-
    compose), soit le jeton en clair d'un AppToken créé via
    POST /api/app-tokens (prod, révocable indépendamment) - les deux
    marchent avec la même variable d'environnement, sans changement de
    code ici."""
    return httpx.Client(
        base_url=f"{settings.BACKEND_INTERNAL_URL}/api/internal",
        headers={"X-App-Token": settings.INTERNAL_WORKER_TOKEN},
        timeout=30.0,
    )


def get_document(client: httpx.Client, document_id: str) -> dict:
    response = client.get(f"/documents/{document_id}")
    response.raise_for_status()
    return response.json()


def set_extraction_status(client: httpx.Client, document_id: str, *, status: str, error: str | None = None) -> dict:
    response = client.put(f"/documents/{document_id}/extraction-status", json={"status": status, "error": error})
    response.raise_for_status()
    return response.json()


def set_file_hash(client: httpx.Client, document_id: str, *, file_hash: str) -> dict:
    """Dépose le hash SHA-256 d'un document, calculé par le worker au moment
    de l'extraction (les bytes sont déjà en mémoire)."""
    response = client.put(f"/documents/{document_id}/file-hash", json={"file_hash": file_hash})
    response.raise_for_status()
    return response.json()


def add_page(
    client: httpx.Client, document_id: str, *, page_number: int, content: str, screenshot_key: str | None = None
) -> dict:
    response = client.post(
        f"/documents/{document_id}/pages",
        json={"page_number": page_number, "content": content, "screenshot_key": screenshot_key},
    )
    response.raise_for_status()
    return response.json()


def add_bounding_box(
    client: httpx.Client, page_id: str, *, x_min: float, y_min: float, x_max: float, y_max: float
) -> dict:
    response = client.post(
        f"/pages/{page_id}/bounding-boxes",
        json={"x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max},
    )
    response.raise_for_status()
    return response.json()


def replace_text_boxes(client: httpx.Client, page_id: str, boxes: list[dict]) -> None:
    """Pose le texte positionné de la page (lignes et mots avec bbox et intervalle de caractères)."""
    response = client.put(f"/pages/{page_id}/text-boxes", json=boxes)
    response.raise_for_status()
