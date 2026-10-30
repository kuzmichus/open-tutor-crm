"""Модель «Ученик задачи» — привязка задачи к ученику.

Связь многие-ко-многим: задача может касаться нескольких учеников,
ученик — участвовать в нескольких задачах. Пара уникальна
(`uq_task_students_pair`), чтобы повторный выбор в форме не создавал
дубль строки.

Обе ссылки каскадны: удаление задачи или ученика убирает связку.
Сама задача при удалении ученика остаётся — в этом смысл отдельной
таблицы, а не колонки `student_id` у задачи.
"""

from uuid import uuid4

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaskStudent(Base):
    """Связка «задача — ученик»."""

    __tablename__ = "task_students"
    __table_args__ = (
        UniqueConstraint("task_id", "student_id", name="uq_task_students_pair"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<TaskStudent task_id={self.task_id!r} "
            f"student_id={self.student_id!r}>"
        )
