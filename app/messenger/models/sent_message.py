"""Модель «Исходящее сообщение бота»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constraints import sql_string_in
from app.database import Base
from app.messenger.services.messengers import MESSENGERS

# Длина адреса совпадает с chat_id приглашений: туда пишутся и числовые
# chat_id Telegram/MAX, и «@канал» Telegram.
RECIPIENT_LENGTH = 64

# Закрытый список статусов доставки: попытка либо удалась, либо нет.
SENT_MESSAGE_STATUSES = ("sent", "error")

SENT_STATUS_LABELS = {
    "sent": "Доставлено",
    "error": "Ошибка",
}


class SentMessage(Base):
    """Журнал исходящих сообщений бота.

    Пишется диспетчером `send_message` на каждую реальную попытку
    доставки — рассылки, приветственные при привязке и будущие
    автонотификации попадают в один журнал без дублирования логики в
    вызывающих кодах. Ученик опознаётся по chat_id привязок и может быть
    неопознанным (чат репетитора, будущие сценарии) — поэтому `NULL`.
    Строка добавляется без commit: транзакцию завершает вызывающий код.
    """

    __tablename__ = "sent_messages"
    __table_args__ = (
        CheckConstraint(
            sql_string_in("messenger", MESSENGERS),
            name="ck_sent_messages_messenger",
        ),
        CheckConstraint(
            sql_string_in("status", SENT_MESSAGE_STATUSES),
            name="ck_sent_messages_status",
        ),
    )

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
    student_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    messenger: Mapped[str] = mapped_column(String(16), nullable=False)
    recipient: Mapped[str] = mapped_column(
        String(RECIPIENT_LENGTH), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<SentMessage id={self.id} tutor_id={self.tutor_id!r} "
            f"messenger={self.messenger!r} status={self.status!r}>"
        )
