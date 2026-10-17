"""Модель «Ключ восстановления пароля»."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PasswordResetToken(Base):
    """Одноразовый ключ восстановления пароля репетитора."""

    __tablename__ = "tutor_password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL = ключ ещё не использован.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<PasswordResetToken id={self.id} tutor_id={self.tutor_id!r}>"
