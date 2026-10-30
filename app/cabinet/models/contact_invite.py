"""Модель «Приглашение контакта в кабинет родителя»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Токен ссылки-приглашения: `secrets.token_urlsafe(32)` даёт 43 символа
# base64url; колонка с запасом — та же оценка, что у приглашения ученика.
TOKEN_LENGTH = 64


class ContactCabinetInvite(Base):
    """Приглашение контакта в кабинет родителя: одноразовая ссылка.

    Зеркало `StudentCabinetInvite` с заменой ученик → контакт (design D1):
    одна строка на контакт, перевыпуск обновляет `token` и `expires_at` —
    прежняя ссылка гасится сама, регистрация заполняет `used_at`. Отдельная
    таблица, а не общая с ученической: у поверхностей свои идентификаторы
    входа и свои страницы регистрации, смешение ролей усложнило бы и
    выборки, и каскады. Удаление контакта или репетитора уносит строку
    каскадом.
    """

    __tablename__ = "contact_cabinet_invites"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Владелец — дублирует владельца контакта: изоляция действия репетитора
    # проверяется одним условием запроса, без JOIN к контактам.
    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Одна активная ссылка на контакт (uq_contact_cabinet_invites_contact).
    contact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contacts.id", ondelete="CASCADE"),
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
            f"<ContactCabinetInvite id={self.id} contact_id={self.contact_id!r} "
            f"used_at={self.used_at!r}>"
        )
