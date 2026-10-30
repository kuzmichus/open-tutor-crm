"""Модель «Приглашение ученика в мессенджер»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constraints import sql_string_in
from app.database import Base
from app.messenger.services.messengers import MESSENGERS

# Ограничения длины, продиктованные Bot API: код одноразовой ссылки —
# 32 символа base64url (Telegram ограничивает payload диплинка 64,
# MAX — 128), сам диплинк вместе с ником бота заведомо короче 255.
CODE_LENGTH = 64
LINK_LENGTH = 255
CHAT_ID_LENGTH = 64
CHAT_LABEL_LENGTH = 200


class StudentMessengerInvite(Base):
    """Приглашение ученика в канал уведомлений репетитора.

    Одна строка на пару «ученик — мессенджер»: пока заполнены
    `invite_code`/`invite_link` — приглашение «в процессе» (ссылка ждёт
    «Запуска» бота учеником), после подтверждения остаются `chat_id` и
    `chat_label` — чат ученика привязан, код погашен. Удаление ученика
    или репетитора уносит приглашение каскадом.
    """

    __tablename__ = "student_messenger_invites"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "messenger",
            name="uq_student_messenger_invites_student_messenger",
        ),
        CheckConstraint(
            sql_string_in("messenger", MESSENGERS),
            name="ck_student_messenger_invites_messenger",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Владелец — дублирует владельца ученика: изоляция проверяется одним
    # условием запроса, без JOIN к ученикам.
    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    messenger: Mapped[str] = mapped_column(String(16), nullable=False)
    # Непустой код — приглашение «в процессе»; после привязки чата
    # обнуляется вместе со ссылкой (код одноразовый).
    invite_code: Mapped[str | None] = mapped_column(
        String(CODE_LENGTH), nullable=True
    )
    invite_link: Mapped[str | None] = mapped_column(
        String(LINK_LENGTH), nullable=True
    )
    # Привязанный чат ученика: сюда диспетчер уведомлений будет
    # доставлять напоминания, когда дойдёт до рассылки ученикам.
    chat_id: Mapped[str | None] = mapped_column(
        String(CHAT_ID_LENGTH), nullable=True
    )
    chat_label: Mapped[str | None] = mapped_column(
        String(CHAT_LABEL_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<StudentMessengerInvite id={self.id} student_id={self.student_id!r} "
            f"messenger={self.messenger!r}>"
        )
