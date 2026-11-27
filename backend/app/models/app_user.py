from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.encrypted import EncryptedString


class AppUser(Base):
    """Annuaire local des personnes connues de l'application (issue #173).

    L'identité est dans Keycloak : il n'existe pas de table d'utilisateurs maîtresse. Cette table en garde une
    **copie minimale** (identifiant, nom, e-mail), mise à jour à chaque connexion, pour pouvoir **proposer** des
    personnes à l'affectation d'un dossier et afficher leur nom. Une personne qui ne s'est jamais connectée
    n'y figure pas : elle ne peut pas recevoir de dossier.

    ``user_id`` est le ``sub`` Keycloak (clé primaire)."""

    __tablename__ = "app_users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    email: Mapped[str] = mapped_column(EncryptedString, nullable=False, default="")
    # Empreinte de l'adresse (`app.core.crypto.email_index`) : la retrouver sans la déchiffrer.
    email_index: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # `groups` : copie des groupes de l'application dont la personne est membre, resynchronisée à chaque changement
    # (`services/memberships.py`). `is_admin` : super admin vu à la dernière connexion. Servent aux calculs faits
    # sans la personne (qui peut recevoir un dossier, agent qui agit en son nom).
    groups: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def id(self) -> str:
        """Nom d'exposition dans l'API (``PersonOut.id``)."""
        return self.user_id
