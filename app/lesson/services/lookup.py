"""Списки выбора цели урока: поиск учеников и групп для селекта.

Только свои репетитора и только активные/новые ученики — архивные
и чужие в выбор не попадают (спека lesson-management, решение D7,
как в group-membership). Пустой `q` (открытие списка по клику без
ввода) возвращает список целиком; ввод фильтрует его по имени
(для группы — по названию) без учёта регистра.

Поиск в Python, а не SQL `LIKE`: SQLite `lower()` не знает кириллицу,
а записей у одного репетитора немного — как в `student/services/students.py`.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.group.models.group import Group
from app.student.models.student import Student
from app.student.services.presentation import student_full_name

# Статусы учеников, которых можно выбрать целью урока: архивные
# не предлагаются (спека lesson-management).
_SELECTABLE_STATUSES = ("new", "active")


def search_students(db: Session, tutor_id: str, q: str = "") -> list[dict]:
    """Активные/новые ученики репетитора: `[{id, name}]` для списка выбора."""
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


def search_groups(db: Session, tutor_id: str, q: str = "") -> list[dict]:
    """Группы репетитора: `[{id, name}]` для списка выбора."""
    stmt = select(Group).where(Group.tutor_id == tutor_id).order_by(
        Group.name, Group.id
    )
    needle = q.strip().casefold()
    return [
        {"id": group.id, "name": group.name}
        for group in db.scalars(stmt).all()
        if not needle or needle in (group.name or "").casefold()
    ]
