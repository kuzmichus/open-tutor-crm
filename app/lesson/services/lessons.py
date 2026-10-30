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
`starts_at` от меньшего к большему (спека lesson-management). Кроме неё
список умеет сортироваться по цели и статусу: колонок, по которым
педагог ищет глазами, три, и все три должны переключаться, иначе
«отметить прошедшие» снова превращается в прокрутку (change
lessons-table-scale).
"""

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import (
    local_week_bounds,
    now_utc,
    today_local,
    to_local,
)
from app.group.models.group import Group
from app.lesson.models.lesson import LESSON_STATUSES, Lesson
from app.lesson.services.unmarked import is_unmarked
from app.student.models.student import Student
from app.tutor.services.clock import as_utc

# Значения фильтра-чипа периода; пусто — «Все» (спека: Все/Сегодня/На этой неделе).
FILTER_PERIODS = ("", "today", "week")

# Значения селекта статуса; пусто — «Все статусы», «unmarked» — прошедшие
# уроки, не отмеченные как проведённые (change unmarked-lessons).
FILTER_STATUSES = ("", "unmarked")

# Колонки, по которым список умеет сортироваться (change lessons-table-scale).
# Ключ — значение query-параметра `sort`, оно же имя колонки в разметке.
SORT_KEYS = ("date", "target", "status")

# Направление сортировки; по умолчанию — по возрастанию (ближайшие сверху).
SORT_DIRECTIONS = ("asc", "desc")


def normalize_period(period: str) -> str:
    """Значение фильтра периода из query: неизвестное схлопывается в «Все»."""
    return period if period in FILTER_PERIODS else ""


def normalize_status(status: str) -> str:
    """Значение селекта статуса из query: неизвестное — «Все статусы»."""
    return status if status in FILTER_STATUSES else ""


def normalize_sort(sort: str) -> str:
    """Колонка сортировки из query: неизвестное — «date» (ближайшие)."""
    return sort if sort in SORT_KEYS else "date"


def normalize_direction(direction: str) -> str:
    """Направление из query: неизвестное — по возрастанию."""
    return direction if direction in SORT_DIRECTIONS else "asc"


def _target_sort_key(row: dict) -> str:
    """Ключ сортировки по цели: имя в нижнем регистре, кириллица тоже.

    Сравнивать строки в SQL через `lower()` нельзя: SQLite не понимает
    кириллицу в `lower()` без ICU, и «Мария» с «мария» разъехались бы по
    разным концам списка. Поэтому ключ считается в Python — там же, где
    идёт поиск.
    """
    name = row["student_name"] or row["group_name"] or ""
    return name.casefold()


def _status_sort_key(row: dict) -> int:
    """Ключ сортировки по статусу: порядок из закрытого списка модели.

    Не по алфавиту: «Запланирован» раньше «Проведён» — это порядок
    `LESSON_STATUSES`, то есть смысл («сначала то, что ещё не сделано»),
    а не случайность перевода.
    """
    status = row["lesson"].status
    return LESSON_STATUSES.index(status) if status in LESSON_STATUSES else len(
        LESSON_STATUSES
    )


def sort_rows(rows: list[dict], sort: str, direction: str) -> list[dict]:
    """Упорядочивает строки по выбранной колонке.

    Дата — по времени начала (тот же порядок, что в SQL: сначала
    ближайшие). Цель и статус — по ключу в Python, потому что кириллица
    в SQLite не приводится к нижнему регистру.

    Вторичный ключ — `id`: у двух уроков одного дня и одного статуса
    иначе не определён порядок, и строки «прыгали» бы между запросами.
    """
    sort = normalize_sort(sort)
    reverse = normalize_direction(direction) == "desc"
    if sort == "target":
        return sorted(
            rows, key=lambda row: (_target_sort_key(row), row["lesson"].id),
            reverse=reverse,
        )
    if sort == "status":
        return sorted(
            rows, key=lambda row: (_status_sort_key(row), row["lesson"].id),
            reverse=reverse,
        )
    return sorted(
        rows,
        key=lambda row: (as_utc(row["lesson"].starts_at), row["lesson"].id),
        reverse=reverse,
    )


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
    status: str = "",
    student_id: str = "",
    sort: str = "date",
    direction: str = "asc",
    tutor,
) -> list[dict]:
    """Строки списка: урок и имена цели — только уроки вошедшего репетитора.

    Строка — `{"lesson": ..., "student_name": ..., "group_name": ...}`.
    `tutor` — карточка владельца: её зона задаёт «сегодня» и границы
    «этой недели» (спека lesson-management, «Фильтры, поиск и сортировка»).
    `sort`/`direction` — выбранный порядок; по умолчанию ближайшие сверху.
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
    status = normalize_status(status)
    # Момент «сейчас» один на всю выборку: строки не должны расходиться
    # в том, что уже «прошло», посреди одного запроса.
    moment = now_utc()

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
        if status == "unmarked" and not is_unmarked(lesson, now=moment):
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
    return sort_rows(rows, sort, direction)
