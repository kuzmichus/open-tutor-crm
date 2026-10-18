"""Модель «Контакт»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Contact(Base):
    """Взрослый контакт репетитора (мама, папа, бабушка, водитель…).

    Хранится отдельно от ученика, чтобы один и тот же человек мог быть
    привязан к нескольким ученикам без копирования полей.
    """

    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Телефон и email необязательны и не уникальны: тёзки и общий номер
    # у сиблингов — легитимные случаи. Хранится исходное написание,
    # нормализация выполняется только для поиска.
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Contact id={self.id} full_name={self.full_name!r}>"
