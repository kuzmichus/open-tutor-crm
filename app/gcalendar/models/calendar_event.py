"""Модель «Событие Google Календаря»: связь урока с событием в Google."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Календарь аккаунта по умолчанию: выбор конкретного календаря в интерфейсе
# не делается, но id хранится — задел на выбор без изменения схемы (D5).
DEFAULT_CALENDAR_ID = "primary"

class CalendarEvent(Base):
    """Строка соответствия «урок → событие Google Календаря».

    Первичный ключ — `lesson_id`: у урока не больше одного события в
    Google. Строка живёт ровно столько же, сколько урок: FK с
    `ON DELETE CASCADE` сносит её вместе с уроком, поэтому удаление
    события в Google обязано случиться **до** удаления урока
    (design D7) — иначе `event_id` потеряется и событие останется
    в календаре навсегда.

    `content_hash` — sha256 канонического тела события: сравнение
    хеша решает «создать / обновить / ничего не делать» без запроса
    к Google, когда урок не менялся (design D4).
    """

    __tablename__ = "calendar_events"

    lesson_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Идентификатор события в Google: длинный base32-подобный id, поэтому
    # колонка с запасом (255 у Google не документировано как предел).
    event_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    calendar_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default=DEFAULT_CALENDAR_ID,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CalendarEvent lesson_id={self.lesson_id!r} "
            f"event_id={self.event_id!r}>"
        )
