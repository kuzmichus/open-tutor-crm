"""Прошедшие уроки без отметки «Проведён».

Урок «не отмечен», если он уже закончился (`starts_at + duration_min` — в
прошлом), но всё ещё «Запланирован». Единый предикат `is_unmarked` — для
баннера-напоминания, фильтра списка «Не отмеченные» и задания cron: три
потребителя не должны расходиться в трактовке (design D3 change'а
unmarked-lessons).

Грубый SQL-префильтр (`starts_at < now`) только сужает выборку: прибавить
длительность к UTC-значению в SQL нельзя — арифметика календарного времени
живёт в зоне педагога, а не в хранилище (design D3 спеки tutor-timezone).
Финально решает предикат в Python над нормализованным `as_utc`.

Окно жизни не отмеченного урока ограничено: через 24 часа после конца его
завершает задание cron (`auto_complete.py`), поэтому выборки остаются малыми.
"""

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import now_utc
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.services.clock import as_utc

def lesson_end(lesson: Lesson) -> datetime:
    """Окончание урока как aware UTC: начало плюс длительность.

    Длительность — минуты, а не календарный интервал, поэтому простое
    сложение с UTC-началом корректно (правила календаря живут в зоне
    педагога и здесь не нужны).
    """
    return as_utc(lesson.starts_at) + timedelta(minutes=lesson.duration_min or 0)


def is_unmarked(lesson: Lesson, *, now: datetime | None = None) -> bool:
    """«Не отмечен»: закончился, но остался в статусе «Запланирован»."""
    if lesson.status != "planned":
        return False
    return lesson_end(lesson) <= (now or now_utc())


def list_unmarked(
    db: Session,
    tutor_id: str,
    tutor,
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Не отмеченные уроки репетитора, от свежих к старым.

    Строка — `{"lesson": ..., "name": ..., "starts_at": ...}`, где `name` —
    имя ученика или группы (для баннера). Изоляция как во всём модуле:
    у `lessons` нет `tutor_id`, владелец выводится из цели через JOIN.
    """
    moment = now or now_utc()
    stmt = (
        select(Lesson, Student.first_name, Student.last_name, Group.name)
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
            Lesson.status == "planned",
            # Грубый префильтр: конец не раньше начала — кто начался после
            # «сейчас», уже не мог закончиться.
            Lesson.starts_at <= as_utc(moment),
        )
        .order_by(Lesson.starts_at.desc(), Lesson.id)
    )

    rows: list[dict] = []
    for lesson, first_name, last_name, group_name in db.execute(stmt).all():
        if not is_unmarked(lesson, now=moment):
            continue
        if lesson.group_id:
            name = group_name or ""
        else:
            name = " ".join(part for part in (first_name, last_name) if part)
        rows.append(
            {
                "lesson": lesson,
                "name": name,
                "starts_at": as_utc(lesson.starts_at),
            }
        )
    return rows
