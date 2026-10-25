"""Модель «Бронь окна» (design.md D3).

Бронь — сущность окна, своего `tutor_id` у неё нет: владелец выводится
через окно (как владелец урока выводится из цели). Поэтому `slot_id`
каскаден, а `student_id`/`lesson_id` объявлены `SET NULL`: удаление
ученика или урока не должно уничтожать историю заявки.

Статусы — закрытый список (AGENTS.md, п. 10): один источник истины для
CHECK-ограничения в БД, для options и для подписей.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constraints import sql_string_in
from app.database import Base

# Статусы брони: активные (pending, confirmed) и завершающие
# (rejected, cancelled). Переход из завершающего статуса невозможен.
BOOKING_STATUSES = ("pending", "confirmed", "rejected", "cancelled")
BOOKING_STATUS_LABELS = {
    "pending": "Ожидает подтверждения",
    "confirmed": "Подтверждена",
    "rejected": "Отклонена",
    "cancelled": "Отменена",
}
# Статусы, при которых окно считается занятым записью (design.md D4).
ACTIVE_BOOKING_STATUSES = ("pending", "confirmed")


class Booking(Base):
    """Заявка ученика на окно для записи.

    Активная бронь на окно — не более одной: это держит частичный
    уникальный индекс `ux_bookings_active_slot` (см. миграцию), а не только
    проверка в сервисе. Гонка двух одновременных заявок не создаст две
    активные брони.
    """

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            sql_string_in("status", BOOKING_STATUSES),
            name="ck_bookings_status",
        ),
        # Одна активная бронь на окно — частичный уникальный индекс
        # (design.md D3): SQLite его поддерживает, и гонка двух заявок
        # не создаст две активные брони. Объявлен и в модели, чтобы
        # `create_all` в тестах держал тот же инвариант, что миграция.
        Index(
            "ux_bookings_active_slot",
            "slot_id",
            unique=True,
            sqlite_where=text(
                sql_string_in("status", ACTIVE_BOOKING_STATUSES)
            ),
            postgresql_where=text(
                sql_string_in("status", ACTIVE_BOOKING_STATUSES)
            ),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Бронь без окна не имеет смысла — каскадное удаление вместе с окном.
    slot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("slots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="pending",
    )
    # Заполняются при подтверждении; SET NULL сохраняет историю заявки,
    # если ученика или урок позже удалили.
    student_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lesson_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    # Момент решения педагога (подтверждение/отклонение/отмена); NULL —
    # бронь ещё ждёт решения.
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Booking id={self.id} slot_id={self.slot_id} "
            f"status={self.status!r}>"
        )
