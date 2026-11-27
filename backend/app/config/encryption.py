from pydantic_settings import BaseSettings


class EncryptionSettings(BaseSettings):
    """Chiffrement en base des noms et des e-mails des personnes (issue #658). Aucune valeur par défaut : une clé
    connue de tous ne protégerait rien."""

    # « identifiant:clé,identifiant:clé » ; chaque clé fait 32 octets en base64 (`openssl rand -base64 32`). La
    # **première** chiffre ; les suivantes ne servent qu'à relire, le temps d'une rotation.
    ENCRYPTION_KEYS: str = ""
    # Clé de l'empreinte des e-mails (même format de 32 octets, sans identifiant), distincte des précédentes.
    EMAIL_INDEX_KEY: str = ""
