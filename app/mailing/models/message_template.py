"""Модель «Шаблон сообщения»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Название шаблона — короткая подпись в селекте и модалке.
TITLE_LENGTH = 200


class MessageTemplate(Base):
    """Сохранённый текст рассылки репетитора.

    Хранит исходный текст с подстановками ({имя}, {баланс}, …) как есть:
    значения подставляются на отправке под конкретного ученика, поэтому
    правка шаблона не меняет уже отправленные сообщения.
    """

    __tablename__ = "message_templates"

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
    title: Mapped[str] = mapped_column(String(TITLE_LENGTH), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<MessageTemplate id={self.id} tutor_id={self.tutor_id!r} "
            f"title={self.title!r}>"
        )
