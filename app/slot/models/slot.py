"""Модель «Окно для записи» (design.md D2).

Окно — корневая сущность репетитора: цели у него нет, поэтому `tutor_id`
живёт отдельной колонкой (как у `students` и `tutor_unavailability`), а не
выводится из цели, как владелец урока.

`duration_min` берётся из того же закрытого списка, что и длительность
урока (`LESSON_DURATIONS`): запись из окна создаёт урок этой длительности,
и значение вне списка сделало бы сохранение урока невозможным.

`UNIQUE(tutor_id, starts_at)` — дешёвая защита от точного дубля, который
пачка могла бы создать при неаккуратных параметрах. Частичное пересечение
(14:00 и 14:10) индекс не ловит — его проверяет сервис занятости.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constraints import sql_int_in
from app.database import Base
from app.lesson.models.lesson import LESSON_DURATIONS


class Slot(Base):
    """Окно для записи: начало в UTC, длительность и признак публичности.

    Моменты времени (`starts_at`, `created_at`, `updated_at`) хранятся в
    UTC; настенное время зоны педагога существует только на входе и на
    выводе (спека tutor-timezone). SQLite теряет tzinfo, поэтому чтения
    нормализуются через `as_utc`.

    Занятость окна отдельным полем не хранится: она вычисляется
    пересечением с уроками и активными бронями (design.md D4).
    """

    __tablename__ = "slots"
    __table_args__ = (
        CheckConstraint(
            sql_int_in("duration_min", LESSON_DURATIONS),
            name="ck_slots_duration",
        ),
        UniqueConstraint("tutor_id", "starts_at", name="uq_slots_tutor_start"),
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
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    # Публичное окно видно ученику на странице записи; приватное — только
    # педагогу в календаре (спека slot-management).
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
            f"<Slot id={self.id} starts_at={self.starts_at!r} "
            f"duration_min={self.duration_min}>"
        )
