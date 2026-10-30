"""Модель «Сессия контакта» (кабинет родителя)."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ContactSession(Base):
    """Серверная сессия входа контакта в кабинет родителя.

    Третья пара «таблица + cookie» (design D4): `parent_session` не
    пересекается ни с `tutor_session`, ни с `student_session`, поэтому все
    три сессии живут в одном браузере независимо. Отзыв = удаление строки:
    «Выход» закрывает кабинет гарантированно. Удаление контакта уносит его
    сессии каскадом.
    """

    __tablename__ = "contact_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ContactSession id={self.id} contact_id={self.contact_id!r}>"
