"""Types de colonnes chiffrées : le chiffrement et le déchiffrement sont faits ici, le reste du code lit du clair.

Une colonne chiffrée **ne se cherche, ne se trie et ne se compare pas en SQL** (deux chiffrements d'une même valeur
diffèrent) : à faire en Python, ou par une empreinte (`app.core.crypto.email_index`)."""

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

from app.core.crypto import decrypt, encrypt

# Marque les objets « personne » d'un contenu JSON, seuls dont le nom est chiffré.
PERSON_MARK = "person"


class EncryptedString(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        return encrypt(value) if value else value

    def process_result_value(self, value: str | None, dialect) -> str | None:
        return decrypt(value) if value else value


class EncryptedText(EncryptedString):
    impl = Text
    cache_ok = True


def person_ref(user_id: str, name: str) -> dict:
    """Une personne dans un contenu JSON (journal d'un dossier) : son nom y sera chiffré."""
    return {"id": user_id, "name": name, PERSON_MARK: True}


def _is_person(value) -> bool:
    return isinstance(value, dict) and value.get(PERSON_MARK) is True and isinstance(value.get("name"), str)


class EncryptedPeopleJSON(TypeDecorator):
    """JSONB dont les personnes de premier niveau (voir `person_ref`) ont leur nom chiffré. La marque est retirée à la
    lecture."""

    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value: dict | None, dialect) -> dict | None:
        if value is None:
            return None
        return {k: {**v, "name": encrypt(v["name"])} if _is_person(v) else v for k, v in value.items()}

    def process_result_value(self, value: dict | None, dialect) -> dict | None:
        if value is None:
            return None
        return {k: {"id": v.get("id"), "name": decrypt(v["name"])} if _is_person(v) else v for k, v in value.items()}
