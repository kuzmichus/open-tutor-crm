"""Модель «Сессия ученика»."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StudentSession(Base):
    """Серверная сессия входа ученика в кабинет.

    Своя таблица и своя cookie (`student_session`), не пересекающиеся с
    репетиторскими: вход и выход ученика не затрагивают сессию репетитора
    в том же браузере, и наоборот (D4). Отзыв = удаление строки, поэтому
    «Выход» закрывает кабинет гарантированно. Удаление ученика уносит его
    сессии каскадом.
    """

    __tablename__ = "student_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
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
        return f"<StudentSession id={self.id} student_id={self.student_id!r}>"
