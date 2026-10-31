"""Модель «Ученик»."""

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Допустимые значения подтипа и статуса. Держим рядом с моделью, чтобы
# CHECK-ограничение и валидация формы ссылались на один источник.
STUDENT_KINDS = ("child", "adult")
STUDENT_STATUSES = ("new", "active", "archived")

# Границы класса: 1–11 включительно (пустое значение = NULL).
MIN_GRADE = 1
MAX_GRADE = 11


class Student(Base):
    """Ученик — обучающийся у репетитора."""

    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('child', 'adult')",
            name="ck_students_kind",
        ),
        CheckConstraint(
            "grade IS NULL OR (grade BETWEEN 1 AND 11)",
            name="ck_students_grade",
        ),
        CheckConstraint(
            "status IN ('new', 'active', 'archived')",
            name="ck_students_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Владелец. Ученик без репетитора не существует; при удалении репетитора
    # его ученики удаляются каскадом.
    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # Email не уникален (дубликаты в CRM легитимны) и необязателен,
    # но индексирован — по нему идёт поиск.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="child")
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Дата рождения — календарная дата; часовой пояс к ней не применяется.
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    school: Mapped[str | None] = mapped_column(String(255), nullable=True)
    level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="new", index=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Цвет цели для календаря: назначается при создании из палитры
    # `app/common/colors.py` и далее не меняется.
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # Напоминания ученику. У контактов такие же три флага живут на привязке
    # «ученик — контакт», а не на самом контакте.
    remind_lesson: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remind_homework: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remind_cancel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Плательщик: NULL — платит сам ученик. ON DELETE SET NULL: удаление
    # контакта не должно оставлять битую ссылку.
    payer_contact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
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
        return f"<Student id={self.id} first_name={self.first_name!r}>"
