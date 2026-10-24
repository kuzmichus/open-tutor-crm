"""Модель «Недоступность репетитора» (спека tutor-unavailability).

Одна таблица на два режима (design.md D1): «Период» (`mode='period'`) —
первый и, возможно, последний день включительно; «Постоянный выходной»
(`mode='weekday'`) — день недели, возможно, до определённой даты.

Кортежи-константы — один источник истины для CHECK-ограничений, для
options селектов и для подписей (AGENTS.md, п. 10). Инварианты держатся
в БД двумя CHECK'ами: строку нельзя сохранить с полями чужого режима,
поэтому nullable-колонки не превращаются в «мусорную» комбинацию.

`tutor_id` — отдельная колонка, а не вывод из цели: у отметки цели нет
вовсе, это корневая сущность репетитора (как `students` и `groups`).
"""

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Режимы отметки: «Период» (даты) и «Постоянный выходной» (день недели).
UNAVAILABILITY_MODES = ("period", "weekday")

# Причины периода — закрытый список (спека «Причины отметки периода»).
PERIOD_REASONS = ("vacation", "sick", "unavailable")

# У постоянного выходного причина всегда одна (спека «Режим „Постоянный
# выходной“ задаёт день недели»): отдельного выбора причины нет.
DAYOFF_REASON = "dayoff"

REASON_LABELS = {
    "vacation": "Отпуск",
    "sick": "Больничный",
    "unavailable": "Недоступен",
    "dayoff": "Выходной",
}

# Дни недели: 0 — понедельник … 6 — воскресенье (как `date.weekday()`).
WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _sql_string_in(column: str, values: tuple[str, ...]) -> str:
    """`column IN ('a', 'b')` — строковый список для CHECK-ограничения."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class TutorUnavailability(Base):
    """Отметка недоступности репетитора: отпуск, больничный, выходной.

    При удалении репетитора его отметки уходят каскадом. Поля другого
    режима всегда NULL — это гарантируют `ck_unavailability_period` и
    `ck_unavailability_weekday`, а не одна только валидация формы.
    """

    __tablename__ = "tutor_unavailability"
    __table_args__ = (
        # Ограничения режимов условные: SQLite склеивает CHECK'и таблицы
        # через AND, поэтому безусловный «period»-CHECK отклонил бы
        # выходной и наоборот. Каждый CHECK проверяет только свой режим
        # (`mode <> ...` пропускает чужой), а допустимость самого режима
        # проверяют оба — `mode IN ('period', 'weekday')`.
        #
        # Режим «Период»: есть первый день, нет полей выходного, причина
        # из списка периода, последний день не раньше первого.
        CheckConstraint(
            "mode IN ('period', 'weekday') AND ("
            "mode <> 'period' OR ("
            "start_date IS NOT NULL AND weekday IS NULL "
            "AND until_date IS NULL "
            f"AND {_sql_string_in('reason', PERIOD_REASONS)} "
            "AND (end_date IS NULL OR end_date >= start_date)))",
            name="ck_unavailability_period",
        ),
        # Режим «Постоянный выходной»: есть день недели, нет дат периода,
        # причина — «Выходной».
        CheckConstraint(
            "mode IN ('period', 'weekday') AND ("
            "mode <> 'weekday' OR ("
            "weekday IS NOT NULL AND weekday BETWEEN 0 AND 6 "
            "AND start_date IS NULL AND end_date IS NULL "
            f"AND reason = '{DAYOFF_REASON}'))",
            name="ck_unavailability_weekday",
        ),
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
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str] = mapped_column(String(12), nullable=False)
    # Режим «Период»: первый день обязателен, последний NULL — бессрочно.
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Режим «Постоянный выходной»: день недели 0–6, «Действует по» может
    # быть пустым — тогда выходной не ограничен сроком.
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
        return (
            f"<TutorUnavailability id={self.id} mode={self.mode!r} "
            f"reason={self.reason!r}>"
        )
