from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Échéance d'acquittement du courtier d'async-api (politique `rebut`, `consumer-timeout`, 30 min) :
#: au-delà, le message est repris et la tâche entièrement refaite, sans que le worker s'en
#: aperçoive. C'est LE plafond dur de toute promesse de durée (contrat de service § 5).
ECHEANCE_ACQUITTEMENT_S = 1800
#: Part de l'échéance que le worker s'autorise ; le reste absorbe l'imprévu (reprise, réseau).
_MARGE_ECHEANCE = 0.6
#: Budget d'une tâche, tout compris : attente du run, transferts, nettoyage.
BUDGET_TACHE_MAX_S = int(ECHEANCE_ACQUITTEMENT_S * _MARGE_ECHEANCE)
#: Transferts d'une tâche au pire : HEAD + GET de `MAX_TOTAL_SIZE_BYTES` depuis le stockage, puis
#: le dépôt multipart — posé pour 100 Mio à 2 Mio/s ; à confirmer par la mesure sur beta.
DELAI_TRANSFERTS_MAX_S = 60
#: Débit minimal supposé vers le backend, pour borner le délai du dépôt multipart.
DEBIT_DEPOT_MIN_OCTETS_S = 2 * 1024 * 1024
#: Nettoyage synchrone d'un run abandonné, au pire : `stop`, `delete` du run, `delete` de l'analyse.
_APPELS_DE_NETTOYAGE = 3

#: Plafond de `ttl_hours` ouvert à la plateforme (7 jours), bien sous les 2 ans de l'API éphémère.
#: Le résultat est rendu dans la réponse et le run supprimé aussitôt (`DELETE_RUN_AFTER_RESULT`) :
#: le TTL ne sert plus qu'à borner la rétention si cette suppression échoue.
TTL_MAX_PLATEFORME = 168
TTL_DEFAUT_PLATEFORME = 24
#: Nombre de documents par tâche, déclaré dans le schéma (`files.maxItems`) : refusé en 422 à la soumission.
MAX_FILES_PLATEFORME = 20


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    # RabbitMQ (AsyncTaskAPI)
    BROKER_URL: str
    IN_QUEUE_NAME: str = "mille_feuille_queue_in"
    OUT_QUEUE_NAME: str = "mille_feuille_queue_out"
    WORKER_CONCURRENCY: int = 2
    HEALTH_CHECK_HOST: str = "0.0.0.0"  # noqa: S104
    HEALTH_CHECK_PORT: int = 8084
    LOG_LEVEL: str = "INFO"
    # Classe de service déclarée dans `config/services.yaml` d'async-api : elle décide si les appels
    # `progress()` sont émis. Absente, la bibliothèque applique son défaut.
    SERVICE_CLASS: str | None = None

    # Stockage objet d'AsyncTaskAPI, où les fichiers sont déposés avant la tâche.
    AWS_ENDPOINT_URL: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_DEFAULT_REGION: str = "fr-par"
    AWS_S3_BUCKET_NAME: str
    AWS_S3_VERIFY: bool = True

    # API mille-feuille (l'API éphémère est appelée avec un token API : X-App-Token).
    MILLEFEUILLE_BASE_URL: str
    MILLEFEUILLE_API_TOKEN: str
    MILLEFEUILLE_REQUEST_TIMEOUT: float = 30.0
    # Le seul appel qui porte les fichiers (dépôt multipart, jusqu'à MAX_TOTAL_SIZE_BYTES) a son propre
    # délai : 30 s suffisent à une interrogation, pas à 100 Mio.
    MILLEFEUILLE_UPLOAD_TIMEOUT: float = 180.0

    # Garde-fous : le worker charge les fichiers en mémoire avant de les envoyer au backend
    # (contrat de service d'async-api, §5 : borner ses consommations).
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024
    MAX_TOTAL_SIZE_BYTES: int = 100 * 1024 * 1024
    MAX_FILES: int = MAX_FILES_PLATEFORME

    # Durée maximale d'attente de la fin d'un run, et fréquence d'interrogation.
    RUN_TIMEOUT_SECONDS: float = 900.0
    POLL_INTERVAL_SECONDS: float = 3.0
    # Supprime le résultat conservé côté mille-feuille une fois renvoyé dans le message `success`.
    DELETE_RUN_AFTER_RESULT: bool = True

    @model_validator(mode="after")
    def _refuser_une_configuration_qui_ne_tient_pas_dans_l_echeance(self) -> Self:
        """Refuser avant de commencer : une configuration qui laisserait une tâche dépasser
        l'échéance d'acquittement ferait refaire le travail en silence (contrat de service § 5)."""
        budget = (
            self.RUN_TIMEOUT_SECONDS + DELAI_TRANSFERTS_MAX_S + _APPELS_DE_NETTOYAGE * self.MILLEFEUILLE_REQUEST_TIMEOUT
        )
        if budget > BUDGET_TACHE_MAX_S:
            msg = (
                f"RUN_TIMEOUT_SECONDS={self.RUN_TIMEOUT_SECONDS} + transferts {DELAI_TRANSFERTS_MAX_S} s + nettoyage "
                f"{_APPELS_DE_NETTOYAGE} × {self.MILLEFEUILLE_REQUEST_TIMEOUT} s = {budget:.0f} s dépasse le budget "
                f"{BUDGET_TACHE_MAX_S} s ({_MARGE_ECHEANCE:.0%} de l'échéance d'acquittement "
                f"{ECHEANCE_ACQUITTEMENT_S} s)."
            )
            raise ValueError(msg)
        if self.MAX_FILE_SIZE_BYTES > self.MAX_TOTAL_SIZE_BYTES:
            msg = (
                f"MAX_FILE_SIZE_BYTES={self.MAX_FILE_SIZE_BYTES} dépasse "
                f"MAX_TOTAL_SIZE_BYTES={self.MAX_TOTAL_SIZE_BYTES}."
            )
            raise ValueError(msg)
        delai_depot = self.MAX_TOTAL_SIZE_BYTES / DEBIT_DEPOT_MIN_OCTETS_S
        if self.MILLEFEUILLE_UPLOAD_TIMEOUT < delai_depot:
            msg = (
                f"MILLEFEUILLE_UPLOAD_TIMEOUT={self.MILLEFEUILLE_UPLOAD_TIMEOUT} s ne laisse pas déposer "
                f"MAX_TOTAL_SIZE_BYTES={self.MAX_TOTAL_SIZE_BYTES} octets à {DEBIT_DEPOT_MIN_OCTETS_S} octets/s "
                f"({delai_depot:.0f} s)."
            )
            raise ValueError(msg)
        if self.POLL_INTERVAL_SECONDS <= 0 or self.WORKER_CONCURRENCY < 1 or self.MAX_FILES < 1:
            msg = "POLL_INTERVAL_SECONDS, WORKER_CONCURRENCY et MAX_FILES doivent être strictement positifs."
            raise ValueError(msg)
        return self


settings = Settings()
