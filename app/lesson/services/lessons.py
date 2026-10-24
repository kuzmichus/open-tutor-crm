"""Выборки уроков для страницы списка: изоляция, фильтры, поиск, порядок.

Изоляция по репетитору: на `lessons` нет `tutor_id` — владелец урока
выводится из цели (у ученика и группы есть `tutor_id`), поэтому выборка
джойнит обе стороны и берёт урок, чья цель — своя. CHECK XOR гарантирует,
что заполнена ровно одна из двух FK, поэтому `or_` сводится к проверке
владельца единственной цели.

Фильтры комбинируются: чип-период (`period`), ученик (`student_id`) и
поиск (`q` — по цели и заметке, без учёта регистра; кириллицу ищем
в Python, как в `student/services/students.py`).

Границы «сегодня» и «этой недели» считаются в зоне педагога
(`today_local`/`local_week_bounds`): урок 23:30 местного остаётся в своём
дне, а не переезжает в следующий из-за смещения UTC.

Сортировка по умолчанию — «Сначала ближайшие»: по времени начала
`starts_at` от меньшего к большему (спека lesson-management).
"""

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import (
    local_week_bounds,
    today_local,
    to_local,
)
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.services.clock import as_utc

# Значения фильтра-чипа периода; пусто — «Все» (спека: Все/Сегодня/На этой неделе).
FILTER_PERIODS = ("", "today", "week")


def normalize_period(period: str) -> str:
    """Значение фильтра периода из query: неизвестное схлопывается в «Все»."""
    return period if period in FILTER_PERIODS else ""


def _matches_search(
    lesson: Lesson, student_name: str | None, group_name: str | None, needle: str
) -> bool:
    """Совпадение с поиском: цель (имя ученика или группы) и заметка."""
    haystack = " ".join(
        part for part in (student_name, group_name, lesson.note) if part
    )
    return needle in haystack.casefold()


def list_lessons(
    db: Session,
    tutor_id: str,
    *,
    q: str = "",
    period: str = "",
    student_id: str = "",
    tutor,
) -> list[dict]:
    """Строки списка: урок и имена цели — только уроки вошедшего репетитора.

    Строка — `{"lesson": ..., "student_name": ..., "group_name": ...}`.
    `tutor` — карточка владельца: её зона задаёт «сегодня» и границы
    «этой недели» (спека lesson-management, «Фильтры, поиск и сортировка»).
    """
    stmt = (
        select(Lesson, Student.first_name, Student.last_name, Group.name)
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id))
    )
    if student_id:
        stmt = stmt.where(Lesson.student_id == student_id)

    # «Сначала ближайшие» — по времени начала, от меньшего к большему.
    lessons = db.execute(stmt.order_by(Lesson.starts_at, Lesson.id)).all()

    needle = q.strip().casefold()
    period = normalize_period(period)

    # Границы считаются в зоне педагога (design D3): «сегодня» — локальная
    # дата, «неделя» — интервал UTC, вычисленный из локального понедельника.
    today = today_local(tutor)
    week_start = week_end = None
    if period == "week":
        monday = today - timedelta(days=today.weekday())
        week_start, week_end = local_week_bounds(monday, tutor)

    rows: list[dict] = []
    for lesson, first_name, last_name, group_name in lessons:
        # День урока — локальный: урок 23:30 местного (19:30 UTC) не
        # переезжает в завтрашний день (спека: «Урок около полуночи»).
        if period == "today" and to_local(lesson.starts_at, tutor).date() != today:
            continue
        if period == "week" and not (
            week_start <= as_utc(lesson.starts_at) < week_end
        ):
            continue
        student_name = (
            " ".join(part for part in (first_name, last_name) if part)
            if first_name
            else None
        )
        if needle and not _matches_search(lesson, student_name, group_name, needle):
            continue
        rows.append(
            {
                "lesson": lesson,
                "student_name": student_name,
                "group_name": group_name,
            }
        )
    return rows
