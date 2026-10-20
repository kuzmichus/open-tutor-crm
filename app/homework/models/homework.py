"""Модель «Домашнее задание урока» (спека homework-management).

Запись ДЗ — ровно одна на урок (1:1): `lesson_id` UNIQUE и каскадное
удаление вместе с уроком или серией. Статусы — закрытый список
(паттерн `LESSON_STATUSES`): один источник истины для CHECK-ограничения
и для options селекта в панели ДЗ.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Закрытый список статусов ДЗ (спека «Статусы ДЗ»): «Не задано» —
# значение по умолчанию, любой статус ставится вручную.
HOMEWORK_STATUSES = (
    "not_assigned",
    "assigned",
    "submitted",
    "checked",
    "not_done",
)
HOMEWORK_STATUS_LABELS = {
    "not_assigned": "Не задано",
    "assigned": "Задано",
    "submitted": "Сдано",
    "checked": "Проверено",
    "not_done": "Не выполнено",
}


def _sql_string_in(column: str, values: tuple[str, ...]) -> str:
    """`column IN ('a', 'b')` — строковый список для CHECK-ограничения."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class Homework(Base):
    """Домашнее задание одного урока: задание, срок, статус и материалы."""

    __tablename__ = "homework"
    __table_args__ = (
        CheckConstraint(
            _sql_string_in("status", HOMEWORK_STATUSES),
            name="ck_homework_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    lesson_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Обязательный текст задания: пустое «Задание» блокируется валидацией.
    assignment: Mapped[str] = mapped_column(Text, nullable=False)
    # Срок сдачи: `datetime-local` как «Начало» урока (design: Open Questions).
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Флаг учёта дедлайна: сохраняется, поведения от него пока нет.
    deadline_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    status: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default="not_assigned",
    )
    # Ссылка на запись урока (видит ученик — с появлением кабинета).
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Заметка педагога (ученику не видна) и комментарий педагога.
    teacher_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
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
            f"<Homework id={self.id} lesson_id={self.lesson_id!r} "
            f"status={self.status!r}>"
        )
