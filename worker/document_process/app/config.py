from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class WorkerSettings(BaseSettings):
    # Broker et résultats Celery. En Kubernetes, le secret `millefeuille-redis` fournit `REDIS_URL` (avec le mot de
    # passe) : à défaut de `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (docker-compose), c'est lui qui sert.
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    BACKEND_INTERNAL_URL: str = "http://localhost:8000"
    INTERNAL_WORKER_TOKEN: str = ""

    # RustFS en local/dev, un bucket S3 réel en prod (voir backend
    # StorageSettings, mêmes noms de variables des deux côtés).
    AWS_ENDPOINT_URL: str = "http://localhost:9000"
    AWS_ACCESS_KEY_ID: str = "rustfsadmin"
    AWS_SECRET_ACCESS_KEY: str = "rustfsadmin"
    AWS_S3_BUCKET_NAME: str = "mille-feuille"

    # Langue Tesseract (ISO 639-2) pour l'OCR des pages scannées par
    # liteparse. "fra" couvre le français par défaut.
    OCR_LANGUAGE: str = "fra"
    TESSDATA_PATH: str | None = None

    # Ce qui lit une page scannée : "tesseract" (l'OCR de liteparse, par défaut) ou "layout" (les pods PaddleOCR :
    # layout PP-DocLayoutV3, texte PP-OCRv5, tableaux SLANet_plus, et le VLM du hub pour décrire images et tableaux).
    # Une page que les pods ne savent pas lire retombe sur Tesseract : le fichier n'échoue que si celui-ci échoue aussi.
    OCR_ENGINE: Literal["tesseract", "layout"] = "tesseract"
    # Files Celery des pods d'OCR (voir app/ocr/) : ce worker leur envoie des tâches, il ne les consomme pas.
    LAYOUT_QUEUE_NAME: str = "document_layout"
    OCR_QUEUE_NAME: str = "document_ocr"
    TABLE_QUEUE_NAME: str = "document_table"
    VISION_QUEUE_NAME: str = "document_vision"
    # Résolution (DPI) à laquelle les pages confiées aux pods sont rendues.
    OCR_PAGE_DPI: int = 200
    # Une page est lue par les pods quand liteparse la dit scannée ou son texte illisible, ou qu'elle a moins de
    # caractères de texte natif que cela et des images (une page blanche n'est pas envoyée).
    OCR_SCANNED_MIN_CHARS: int = 20
    # Pages d'un document entre les mains des pods en même temps (son layout, puis son texte). La tâche attend :
    # la file d'un pod ne contient jamais plus que cela d'un document.
    OCR_PAGE_WINDOW: int = 4
    # Durée maximale d'une étape d'une page, depuis son envoi - l'attente dans la file comprise. Au-delà, la page
    # retombe sur l'OCR de liteparse.
    OCR_STAGE_TIMEOUT_SECONDS: int = 15 * 60
    OCR_POLL_SECONDS: float = 0.5
    # `true` : les cellules d'un tableau sont lues comme du texte, une ligne par ligne. `false` : le pod `table` en lit
    # la structure et le tableau est écrit en Markdown dans la page.
    OCR_READ_TABLES_AS_TEXT: bool = False
    # Score minimal d'un tableau lu par le pod `table` pour être dit fiable ; en dessous il est gardé, signalé douteux.
    OCR_TABLE_MIN_SCORE: float = 0.6
    # Description des images et des tableaux par le VLM du hub (pod `vision`). Désactivé tant que le pod n'est pas là.
    VISION_POD_ENABLED: bool = False
    # Modèle du hub qui décrit ; vide : le `VLM_MODEL` du pod.
    CAPTION_MODEL: str = ""
    # Une image est décrite quand son petit côté fait au moins ce nombre de pixels de la page (un filet, une puce ou
    # un tampon ne valent pas une description), et seules les CAPTION_MAX_PER_PAGE plus grandes d'une page le sont.
    CAPTION_MIN_PIXELS: int = 96
    CAPTION_MAX_PER_PAGE: int = 5
    CAPTION_MAX_PER_DOCUMENT: int = 50
    # Un tableau lu comme tableau est décrit aussi.
    CAPTION_TABLES: bool = True
    # Une description reste courte dans le texte de la page : coupée ici, à un mot.
    CAPTION_MAX_CHARS: int = 600
    # Durée maximale des descriptions d'une page. Au-delà, la page est gardée sans elles - elle n'est pas relue.
    CAPTION_STAGE_TIMEOUT_SECONDS: int = 5 * 60
    # Limite dure d'une tâche (secondes). Les pods d'OCR rendent une page en quelques secondes mais la tâche les
    # attend : un document scanné de plusieurs dizaines de pages dépasse largement la limite de Tesseract.
    TASK_TIME_LIMIT_SECONDS: int = 0

    @property
    def task_time_limit(self) -> int:
        return self.TASK_TIME_LIMIT_SECONDS or (3600 if self.OCR_ENGINE == "layout" else 300)

    model_config = SettingsConfigDict(case_sensitive=True, env_file=(".env", ".env.local"), extra="ignore")

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL or DEFAULT_REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL or DEFAULT_REDIS_URL


settings = WorkerSettings()
