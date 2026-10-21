"""Недельная выборка уроков репетитора для сетки календаря (design.md D1).

Изоляция по репетитору повторяет `lesson/services/lessons.py::list_lessons`:
на `lessons` нет `tutor_id`, владелец выводится из цели, поэтому выборка
джойнит ученика и группу и берёт урок, чья цель принадлежит репетитору.
Окно недели — `[monday, monday + 7 дней)` по `starts_at` (D1: урок,
начавшийся в воскресенье, в следующую неделю не попадает).
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.calendar.services.week_lesson import WeekLesson
from app.common.colors import DEFAULT_TARGET_COLOR
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student


def week_bounds(monday: date) -> tuple[datetime, datetime]:
    """Границы окна недели: понедельник 00:00 — следующий понедельник 00:00."""
    start = datetime.combine(monday, time.min)
    return start, start + timedelta(days=7)


def _target_name(first_name: str | None, last_name: str | None) -> str:
    """Имя ученика для карточки: «Иван И.» — имя и первая буква фамилии."""
    if not first_name:
        return ""
    initial = f"{last_name[0]}." if last_name else ""
    return " ".join(part for part in (first_name, initial) if part)


def week_lessons(db: Session, tutor_id: str, monday: date) -> list[WeekLesson]:
    """Уроки недели `monday` только этого репетитора, по времени начала."""
    start, end = week_bounds(monday)
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
