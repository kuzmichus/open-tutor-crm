"""Модель «Урок»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Закрытый список типов урока (спека: «Индивидуальный», «Групповой»,
# «Пробный», «Отработка»). Как в student.py: один источник истины —
# для CHECK-ограничения и для options селекта в форме.
LESSON_TYPES = ("individual", "group", "trial", "practice")
LESSON_TYPE_LABELS = {
    "individual": "Индивидуальный",
    "group": "Групповой",
    "trial": "Пробный",
    "practice": "Отработка",
}

# Закрытый список длительностей в минутах (15 значений). Иное значение
# отклоняется CHECK-ограничением и валидацией формы.
LESSON_DURATIONS = (
    30,
    35,
    40,
    45,
    50,
    55,
    60,
    65,
    70,
    75,
    90,
    105,
    120,
    150,
    180,
)

# Статусы (паттерн STUDENT_STATUSES): «Запланирован» / «Проведён».
LESSON_STATUSES = ("planned", "completed")
LESSON_STATUS_LABELS = {
    "planned": "Запланирован",
    "completed": "Проведён",
}

# Оценка для семьи: 1–5 звёзд, NULL — без оценки.
MIN_LESSON_RATING = 1
MAX_LESSON_RATING = 5


def _sql_string_in(column: str, values: tuple[str, ...]) -> str:
    """`column IN ('a', 'b')` — строковый список для CHECK-ограничения."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _sql_int_in(column: str, values: tuple[int, ...]) -> str:
    """`column IN (1, 2)` — числовой список для CHECK-ограничения."""
    joined = ", ".join(str(value) for value in values)
    return f"{column} IN ({joined})"


class Lesson(Base):
    """Урок репетитора: индивидуальный, групповой, пробный или отработка.

    Моменты времени (`starts_at`, `created_at`, `updated_at`) хранятся в
    UTC; настенное время зоны педагога — только на входе и на выводе
    (спека tutor-timezone).

    Ровно одна цель урока — ученик XOR группа — обеспечивается
    CHECK-ограничением на уровне БД (решение D3). Владелец урока
    выводится из цели (у ученика и группы есть `tutor_id`), отдельной
    колонки `tutor_id` нет.

    Удаление ученика, группы или серии каскадом удаляет её уроки:
    SET NULL нарушил бы XOR-проверку (строка осталась бы без цели).
    """

    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint(
            _sql_string_in("type", LESSON_TYPES),
            name="ck_lessons_type",
        ),
        # XOR: ровно одна из двух FK заполнена. В SQLite нет оператора
        # XOR, поэтому через сравнение булевых выражений.
        CheckConstraint(
            "(student_id IS NOT NULL) <> (group_id IS NOT NULL)",
            name="ck_lessons_target_xor",
        ),
        CheckConstraint(
            _sql_int_in("duration_min", LESSON_DURATIONS),
            name="ck_lessons_duration",
        ),
        CheckConstraint(
            _sql_string_in("status", LESSON_STATUSES),
            name="ck_lessons_status",
        ),
        CheckConstraint(
            f"rating IS NULL OR (rating BETWEEN {MIN_LESSON_RATING} "
            f"AND {MAX_LESSON_RATING})",
            name="ck_lessons_rating",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Ровно одна цель (XOR): NULL у «другой» стороны.
    student_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    group_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Член серии; NULL — одиночный урок.
    series_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("lesson_series.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default="individual",
    )
    # Начало урока хранится в UTC (aware, смещение 0): ввод формы трактуется
    # как настенное время в зоне педагога и переводится на сервере, показ —
    # обратный перевод на выводе (спека tutor-timezone). Тип колонки не
    # менялся: DateTime(timezone=True) стоял с самого начала, меняется
    # только то, что в неё кладут. SQLite теряет tzinfo, поэтому чтение
    # нормализуется через `as_utc`.
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    # Заметка репетитору (видит только он).
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Постоянная ссылка на встречу (видеоконференция).
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Оплата ученика, рубли. NULL — цена не задана; у группового урока
    # в списке отображается «—», независимо от значения.
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="planned",
    )
    # Блок «Для семьи»: оценка 1–5 и комментарий для семьи.
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    family_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
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
            f"<Lesson id={self.id} type={self.type!r} "
            f"starts_at={self.starts_at!r}>"
        )
