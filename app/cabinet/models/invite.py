"""Модель «Приглашение в личный кабинет»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Токен ссылки-приглашения: `secrets.token_urlsafe(32)` даёт 43 символа
# base64url; колонка с запасом, как у ключей восстановления репетитора.
TOKEN_LENGTH = 64


class StudentCabinetInvite(Base):
    """Приглашение ученика в личный кабинет: одноразовая ссылка на регистрацию.

    Одна строка на ученика: пока `used_at` пуст и срок не вышел, ссылка
    `/invite/<token>` ждёт регистрации. Перевыпуск обновляет `token` и
    `expires_at` — прежняя ссылка гасится сама (семантика приглашений
    в мессенджеры); регистрация заполняет `used_at` и служит аудитом
    «вход создан по приглашению». Приглашение живёт до появления входа
    (строки `StudentAccess` ещё может не быть) и гасится независимо
    от него (D2). Удаление ученика или репетитора уносит строку каскадом.
    """

    __tablename__ = "student_cabinet_invites"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Владелец — дублирует владельца ученика: изоляция действия репетитора
    # проверяется одним условием запроса, без JOIN к ученикам.
    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Одна активная ссылка на ученика (uq_student_cabinet_invites_student).
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    token: Mapped[str] = mapped_column(
        String(TOKEN_LENGTH), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL = ссылка ещё не погашена регистрацией.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<StudentCabinetInvite id={self.id} student_id={self.student_id!r} "
            f"used_at={self.used_at!r}>"
        )
