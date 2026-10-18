"""Модель «Привязка контакта к ученику»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StudentContact(Base):
    """Связь ученик ↔ контакт с ролью и настройками напоминаний.

    Роль и три флага напоминаний живут именно на привязке: одна мама двух
    детей может получать напоминания о домашке по младшему и не получать
    по старшему.
    """

    __tablename__ = "student_contacts"
    __table_args__ = (
        UniqueConstraint("student_id", "contact_id", name="uq_student_contacts_pair"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Свободный текст: «мама», «папа», «бабушка», «водитель» — без
    # фиксированного списка и без нормализации.
    relation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    remind_lesson: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remind_homework: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remind_cancel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<StudentContact id={self.id} student_id={self.student_id!r} "
            f"contact_id={self.contact_id!r}>"
        )
