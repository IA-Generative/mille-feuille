import enum

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.encrypted import EncryptedString


class ReportType(enum.StrEnum):
    BUG = "bug"
    IDEA = "idea"
    QUESTION = "question"


class ReportStatus(enum.StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"


class Report(UUIDMixin, TimestampMixin, Base):
    """Signalement libre (bug/idée/question) envoyé par un utilisateur depuis
    le menu utilisateur - distinct de Feedback (pouce haut/bas sur un
    message précis) : un Report n'est lié à aucun message, peut porter sur
    n'importe quoi, et suit un cycle de vie statut/réponse piloté par un
    admin."""

    __tablename__ = "reports"

    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    # Résolu une fois à la création, jamais un sub Keycloak brut dans la vue
    # admin, et stable même si l'auteur change son profil ensuite.
    user_display: Mapped[str] = mapped_column(EncryptedString, nullable=False)

    type: Mapped[ReportType] = mapped_column(Enum(ReportType, name="report_type"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"), nullable=False, default=ReportStatus.NEW
    )

    # Capture d'écran optionnelle jointe à la soumission - clé S3, jamais
    # l'URL elle-même (voir GET /reports/{id}/screenshot, même principe que
    # les captures de page de dossier).
    screenshot_key: Mapped[str | None] = mapped_column(String, nullable=True)

    # Une seule réponse, pas un fil de discussion - décision de scope v1
    # (comme Muffin), extensible en fil plus tard si besoin.
    admin_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_by: Mapped[str | None] = mapped_column(String, nullable=True)

    @property
    def has_screenshot(self) -> bool:
        return self.screenshot_key is not None
