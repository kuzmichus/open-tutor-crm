"""Списки выбора учеников задачи: фильтр доски и поле «Привязать к ученику».

Только свои активные и новые ученики: архивные в выбор не попадают —
задача им уже не ставится (то же правило, что у целей урока). Пустой
запрос возвращает список целиком; ввод фильтрует по имени в Python
(SQLite `lower()` не знает кириллицу, а учеников у одного репетитора
немного — как в `student/services/students.py`).

Варианты для виджета `createPersonPicker` (`picker.js`) — `[{id, name}]`;
фильтр доски получает те же варианты и рисует их обычным `<option>`.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.student.models.student import Student
from app.student.services.presentation import student_full_name

# Статусы учеников, которых можно привязать к задаче.
_SELECTABLE_STATUSES = ("new", "active")


def student_options(db: Session, tutor_id: str, q: str = "") -> list[dict]:
    """Активные/новые ученики репетитора: `[{id, name}]` для списков выбора."""
    stmt = (
        select(Student)
        .where(
            Student.tutor_id == tutor_id,
            Student.status.in_(_SELECTABLE_STATUSES),
        )
        .order_by(Student.first_name, Student.last_name, Student.id)
    )
    needle = q.strip().casefold()
    options: list[dict] = []
    for student in db.scalars(stmt).all():
        name = student_full_name(student)
        if needle and needle not in name.casefold():
            continue
        options.append({"id": student.id, "name": name})
    return options
