"""Модель «Серия уроков» — повторяющееся расписание."""

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import JSON, Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Интервал повтора по умолчанию — еженедельно; панель расписания
# позволяет выбрать и большее значение.
DEFAULT_INTERVAL_WEEKS = 1


class LessonSeries(Base):
    """Серия повторяющихся уроков.

    Слоты хранятся одной JSON-колонкой (решение D1): список объектов
    `{"weekday": 0..6, "start_time": "HH:MM", "end_time": "HH:MM"}` —
    слоты нужны только для генерации уроков и панели расписания,
    в запросах они не участвуют.

    Уроки материализуются при создании серии и ссылаются на неё через
    `lessons.series_id`: удаление серии каскадом уносит её уроки.
    """

    __tablename__ = "lesson_series"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Список слотов: день недели + начало/окончание. Пустой список —
    # валидационная ошибка на уровне сервиса (см. design D2), не БД.
    slots: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    # Через сколько недель повторяются слоты (1 = каждую неделю).
    interval_weeks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_INTERVAL_WEEKS,
    )
    # Дата окончания (включительно). NULL — только у серии без повтора;
    # повтор без этой даты блокируется валидацией формы.
    until_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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
        return f"<LessonSeries id={self.id} interval_weeks={self.interval_weeks}>"
