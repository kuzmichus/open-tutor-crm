"""Модель «Посещаемость урока» — отметка участника группового урока."""

from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constraints import sql_string_in
from app.database import Base

# Закрытый список причин неявки (паттерн LESSON_TYPES): источник истины
# для CHECK-ограничения и для options селекта причины в форме.
# Причина на деньги не влияет (спека lesson-attendance) — только пометка
# репетитора для будущей статистики.
ABSENCE_REASONS = ("no_reason", "excused")
ABSENCE_REASON_LABELS = {
    "no_reason": "Без причины",
    "excused": "Уважительная",
}


class LessonAttendance(Base):
    """Отметка присутствия участника группового урока.

    По записи на пару «урок, ученик» (`UNIQUE`); у индивидуального,
    пробного и отработочного уроков отметок нет — блок «Присутствие»
    вводится только у группового (Non-Goals design'а).

    Инвариант `reason`: у присутствовавшего причины нет, у отсутствовавшего
    она обязательна и берётся из закрытого списка — CHECK-ограничение не
    пускает значение, которого нет в форме.

    Урок без отметок трактуется как «все присутствовали» (design D2):
    существующие уроки при пересохранении денег не меняют. Записи
    присутствовавших хранить можно — на цели списаний они не влияют.

    Владелец выводится из владельца урока, отдельной колонки `tutor_id`
    нет: чтение и запись идут только через `get_owned_lesson`.
    """

    __tablename__ = "lesson_attendance"
    __table_args__ = (
        UniqueConstraint("lesson_id", "student_id", name="uq_lesson_attendance_pair"),
        CheckConstraint(
            "(present AND reason IS NULL) "
            "OR ((NOT present) AND "
            + sql_string_in("reason", ABSENCE_REASONS)
            + ")",
            name="ck_lesson_attendance_reason",
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
        index=True,
    )
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # False — отсутствовал (обязательна причина), True — присутствовал.
    present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<LessonAttendance lesson_id={self.lesson_id} "
            f"student_id={self.student_id} present={self.present}>"
        )
