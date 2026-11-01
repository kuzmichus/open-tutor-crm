"""Выборка учеников с днём рождения в заданный день.

Месяц и день сравниваются в Python, а не в SQL: функции извлечения части
даты различаются между SQLite и PostgreSQL, а карточек у одного
репетитора немного — тот же приём, что и в поиске `list_students`.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.student.models.student import Student

def birthday_students(
    db: Session,
    tutor_id: str,
    day: date,
    *,
    include_archived: bool = False,
) -> list[Student]:
    """Ученики репетитора, у которых день рождения приходится на `day`.

    Архивные по умолчанию исключены: рассылка — про текущих учеников.
    Фильтра по подтипу (`kind`) нет: взрослому ученику поздравление нужно
    так же, как ребёнку. Порядок — по фамилии (`COALESCE(last_name,
    first_name)`), как в списке учеников.
    """
    stmt = select(Student).where(
        Student.tutor_id == tutor_id,
        Student.birth_date.is_not(None),
    )
    if not include_archived:
        stmt = stmt.where(Student.status != "archived")
    stmt = stmt.order_by(
        func.coalesce(Student.last_name, Student.first_name),
        Student.first_name,
    )
    return [
        student
        for student in db.scalars(stmt).all()
        if (student.birth_date.month, student.birth_date.day) == (day.month, day.day)
    ]

def age_on(birth_date: date, day: date) -> int | None:
    """Сколько лет исполняется в день `day`; `None` — возраст неизвестен.

    Год рождения в будущем (данные из будущего или ошибка ввода) даёт
    `None`: отрицательный возраст в сообщении выглядел бы поломкой.
    """
    if birth_date > day:
        return None
    return day.year - birth_date.year
