"""Модель «Вход контакта» (кабинет родителя)."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Минимальная длина пароля — общий источник истины с входом ученика:
# требование одинаковое, и дублировать константу вторым числом нельзя.
# Импорт помещён рядом с моделью, чтобы CHECK и валидация формы видели
# одно значение (см. `MIN_PASSWORD_LENGTH` в `student_access`).
from app.student.models.student_access import MIN_PASSWORD_LENGTH  # noqa: F401


class ContactAccess(Base):
    """Вход контакта в кабинет родителя: email и хеш пароля.

    Отличия от `StudentAccess` (design D1): без колонки `login` — вход
    заводится только по приглашению, и email здесь единственная
    идентичность; когда появится ручная модалка, это миграция на колонку.
    Уникальность email глобальная: кабинет входит по паре «email + пароль»
    без указания репетитора, поэтому один адрес не должен встречаться у
    двух входов. `contact_id` уникален — у контакта ровно один вход;
    удаление контакта каскадом уносит вход.
    """

    __tablename__ = "contact_access"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Ровно один вход на контакт (uq_contact_access_contact).
    contact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # Формат `pbkdf2_sha256$итерации$соль$хеш` (PasswordHasher).
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
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
        return f"<ContactAccess id={self.id} contact_id={self.contact_id!r}>"
