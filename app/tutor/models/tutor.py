"""Модель «Репетитор»."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Tutor(Base):
    """Репетитор — владелец учеников и занятий в CRM."""

    __tablename__ = "tutors"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Пароль хранится только в захешированном виде (см. app.tutor.services.password_hasher).
    # Nullable: у строк, перенесённых миграцией из старой схемы, пароля ещё нет.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str | None] = mapped_column(String(100), nullable=True)
    experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Tutor id={self.id} name={self.name!r}>"
