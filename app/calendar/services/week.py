"""Недельная выборка уроков репетитора для сетки календаря (design.md D1).

Изоляция по репетитору повторяет `lesson/services/lessons.py::list_lessons`:
на `lessons` нет `tutor_id`, владелец выводится из цели, поэтому выборка
джойнит ученика и группу и берёт урок, чья цель принадлежит репетитору.
Окно недели — `[monday, monday + 7 дней)` по `starts_at` (D1: урок,
начавшийся в воскресенье, в следующую неделю не попадает).

Границы окна считаются как настенное время в зоне педагога и переводятся в
UTC по отдельности (`local_week_bounds`, design D3): прибавление
`timedelta` к UTC-значению сломало бы неделю с переводом часов.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.calendar.services.week_lesson import WeekLesson
from app.common.colors import DEFAULT_TARGET_COLOR
from app.common.services.tutor_time import local_week_bounds
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student


def week_start(value: date | str) -> date:
    """Понедельник недели, содержащей `value` (строка — дата в формате ISO).

    Некорректная строка — ValueError: вызывающая сторона (вьюха) сама
    решает, чем заменить кривой `?start=` (обычно — текущей неделей).
    Функция переехала сюда из удалённого демо-генератора: это живое
    поведение календаря, а не демо-данные (design.md D7).
    """
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value - timedelta(days=value.weekday())


def week_bounds(monday: date, tutor) -> tuple[datetime, datetime]:
    """Границы окна недели как aware UTC: пн 00:00 — следующий пн 00:00.

    Обе границы считаются настенным временем в зоне педагога и переводятся
    по отдельности (`local_week_bounds`, design D3): единый сдвиг не
    учитывает перевод часов, а неделя с переводом короче или длиннее семи
    суток ровно на час.
    """
    return local_week_bounds(monday, tutor)


def _target_name(first_name: str | None, last_name: str | None) -> str:
    """Имя ученика для карточки: «Иван И.» — имя и первая буква фамилии."""
    if not first_name:
        return ""
    initial = f"{last_name[0]}." if last_name else ""
    return " ".join(part for part in (first_name, initial) if part)


def week_lessons(
    db: Session, tutor_id: str, monday: date, tutor
) -> list[WeekLesson]:
    """Уроки недели `monday` только этого репетитора, по времени начала.

    `tutor` — карточка репетитора: её зона задаёт границы окна недели
    (aware UTC), а `starts_at` хранится в UTC (спека tutor-timezone).
    """
    start, end = week_bounds(monday, tutor)
    stmt = (
        select(
            Lesson,
            Student.first_name,
            Student.last_name,
            Student.color,
            Group.name,
            Group.color,
        )
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
        .order_by(Lesson.starts_at, Lesson.id)
    )

    rows: list[WeekLesson] = []
    for lesson, first_name, last_name, student_color, group_name, group_color in (
        db.execute(stmt).all()
    ):
        # CHECK XOR гарантирует ровно одну заполненную цель.
        if lesson.group_id:
            rows.append(
                WeekLesson(
                    lesson=lesson,
                    target_name=group_name or "",
                    target_id=lesson.group_id,
                    target_color=group_color or DEFAULT_TARGET_COLOR,
                )
            )
        else:
            rows.append(
                WeekLesson(
                    lesson=lesson,
                    target_name=_target_name(first_name, last_name),
                    target_id=lesson.student_id or "",
                    target_color=student_color or DEFAULT_TARGET_COLOR,
                )
            )
    return rows
