"""Занятость окна: вычисление пересечением, а не хранение (design.md D4).

Состояние окна выводится по текущим данным:

    booking  -> есть активная бронь (pending | confirmed)
    lesson   -> существует урок репетитора, пересекающийся по времени
    past     -> окно уже закончилось
    free     -> иначе

Приоритет подписи — `booking > lesson > past > free`. Подтверждённая бронь
это договорённость с человеком, её нельзя спрятать за словом «прошло»; урок
в прошлом полезнее показать как «занято уроком» тому, кто разбирается,
почему время ушло.

*Почему не колонка*: урок появляется четырьмя путями (форма, серия,
перетаскивание, подтверждение брони). Хранимое поле `is_busy` пришлось бы
обновлять в каждом из них и разошлось бы при первом пропущенном вызове.

Пересечение считается как полуинтервалы `[start, start + duration)`:
касание границ занятостью не является (окно 14:00–14:40 и урок 14:40–15:20
не конфликтуют).
"""

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.booking.models.booking import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
)
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.slot.models.slot import Slot
from app.student.models.student import Student
from app.tutor.services.clock import as_utc

# Машинные значения состояний окна. Подписи для шаблона живут в
# `presentation.py`, чтобы модель/сервис не тащили текст интерфейса.
SLOT_FREE = "free"
SLOT_PENDING = "pending"
SLOT_BOOKED = "booking"
SLOT_LESSON = "lesson"
SLOT_PAST = "past"

SLOT_STATES = (SLOT_FREE, SLOT_PENDING, SLOT_BOOKED, SLOT_LESSON, SLOT_PAST)

# Виды конфликта времени: с чем пересекается проверяемый интервал. Одна
# пара значений на все проверки записи — создание окна, перенос окна и
# подтверждение брони (design.md D9, шаг 3).
CONFLICT_LESSON = "lesson"
CONFLICT_SLOT = "slot"

# Максимальная длительность урока из закрытого списка: по ней строится
# нижняя граница выборки «уроки, которые ещё могут пересечься».
_MAX_LESSON_MIN = 180


def slot_end(slot: Slot) -> datetime:
    """Конец окна (aware UTC): начало + длительность."""
    return as_utc(slot.starts_at) + timedelta(minutes=slot.duration_min or 0)


def overlaps(
    start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
) -> bool:
    """Пересекаются ли полуинтервалы `[start_a, end_a)` и `[start_b, end_b)`.

    Касание границ пересечением не считается: окно 14:00–14:40 и урок
    14:40–15:20 не конфликтуют. Общая функция — чтобы пачка (`batch.py`)
    и состояние окна (`slot_states`) считали пересечение одинаково.
    """
    return start_a < end_b and start_b < end_a


def lesson_spans(lessons: list[Lesson]) -> list[tuple[datetime, datetime]]:
    """Интервалы уроков `[начало, конец)` в aware UTC.

    SQLite теряет tzinfo, поэтому начало нормализуется через `as_utc`.
    """
    spans: list[tuple[datetime, datetime]] = []
    for lesson in lessons:
        lesson_start = as_utc(lesson.starts_at)
        spans.append(
            (lesson_start, lesson_start + timedelta(minutes=lesson.duration_min or 0))
        )
    return spans


def slot_spans(slots: list[Slot]) -> list[tuple[datetime, datetime]]:
    """Интервалы окон `[начало, конец)` в aware UTC."""
    return [(as_utc(slot.starts_at), slot_end(slot)) for slot in slots]


def _overlap_condition(column, start: datetime, end: datetime):
    """Условие «урок, начинающийся в `column`, пересекается с [start, end)».

    `column + duration > start` в SQL для дат неудобно, поэтому нижняя
    граница берётся с запасом по максимальной длительности урока, а точное
    пересечение досчитывается в Python — одним проходом, без N+1.
    """
    return column >= start - timedelta(minutes=_MAX_LESSON_MIN), column < end


def lessons_for_range(
    db: Session, tutor_id: str, start: datetime, end: datetime
) -> list[Lesson]:
    """Уроки репетитора, которые могут пересечься с `[start, end)`.

    Один `SELECT` на весь диапазон: владелец урока выводится из цели
    (ученик или группа), поэтому выборка джойнит обе таблицы — как
    `calendar/services/week.py::week_lessons`.
    """
    lower, upper = _overlap_condition(Lesson.starts_at, start, end)
    stmt = (
        select(Lesson)
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
            lower,
            upper,
        )
        .order_by(Lesson.starts_at, Lesson.id)
    )
    return list(db.scalars(stmt))


def slots_for_range(
    db: Session, tutor_id: str, start: datetime, end: datetime
) -> list[Slot]:
    """Окна репетитора, которые могут пересечься с `[start, end)`.

    Нижняя граница берётся с запасом по максимальной длительности окна:
    окно, начавшееся до `start`, но заканчивающееся внутри диапазона,
    обязано попасть в выборку (иначе проверка пересечения при создании и
    переносе пропустила бы частичное наложение).
    """
    lower, upper = _overlap_condition(Slot.starts_at, start, end)
    stmt = (
        select(Slot)
        .where(Slot.tutor_id == tutor_id, lower, upper)
        .order_by(Slot.starts_at, Slot.id)
    )
    return list(db.scalars(stmt))


def active_bookings(db: Session, slot_ids: list[str]) -> dict[str, Booking]:
    """Активные брони по окнам: `slot_id → Booking`. Один запрос на список.

    На окно не может быть двух активных броней (частичный уникальный
    индекс `ux_bookings_active_slot`), поэтому словарь однозначен.
    """
    if not slot_ids:
        return {}
    rows = db.scalars(
        select(Booking)
        .where(
            Booking.slot_id.in_(slot_ids),
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .order_by(Booking.created_at, Booking.id)
    )
    return {booking.slot_id: booking for booking in rows}


def conflicts(
    db: Session,
    tutor_id: str,
    start: datetime,
    end: datetime,
    *,
    exclude_slot_id: str | None = None,
) -> list[str]:
    """С чем пересекается интервал `[start, end)`: уроки и/или другие окна.

    Возвращает машинные виды конфликта (`CONFLICT_LESSON`,
    `CONFLICT_SLOT`) в порядке приоритета: урок информативнее окна, потому
    что лечится иначе. Пустой список — время свободно.

    `exclude_slot_id` — само окно: без исключения оно пересекалось бы с
    собой. Одна функция на все проверки записи (создание окна, перенос,
    подтверждение брони) — чтобы «занято» везде означало одно и то же.
    """
    kinds: list[str] = []
    lessons = lessons_for_range(db, tutor_id, start, end)
    if any(
        overlaps(start, end, lesson_start, lesson_end)
        for lesson_start, lesson_end in lesson_spans(lessons)
    ):
        kinds.append(CONFLICT_LESSON)

    nearby = slots_for_range(db, tutor_id, start, end)
    if any(
        overlaps(start, end, slot_start, slot_end)
        for slot, (slot_start, slot_end) in zip(
            nearby, slot_spans(nearby), strict=True
        )
        if slot.id != exclude_slot_id
    ):
        kinds.append(CONFLICT_SLOT)
    return kinds

def _intersects_lesson(
    lessons: list[Lesson], start: datetime, end: datetime
) -> bool:
    """Пересекается ли `[start, end)` хотя бы с одним уроком.

    Полуинтервалы: `lesson.starts_at < end AND lesson_end > start`.
    """
    for lesson in lessons:
        lesson_start = as_utc(lesson.starts_at)
        lesson_end = lesson_start + timedelta(minutes=lesson.duration_min or 0)
        if lesson_start < end and lesson_end > start:
            return True
    return False


def slot_states(
    db: Session,
    tutor_id: str,
    slots: list[Slot],
    now: datetime,
) -> dict[str, str]:
    """Состояние каждого окна: `slot_id → free | pending | booking | lesson | past`.

    Запросов ровно два независимо от числа окон (уроки диапазона + активные
    брони), поэтому рендер недели не растёт с числом окон (design.md
    Risks: «Пересечения считаются по уже загруженным строкам»).
    """
    if not slots:
        return {}

    starts = [as_utc(slot.starts_at) for slot in slots]
    start = min(starts)
    end = max(
        as_utc(slot.starts_at) + timedelta(minutes=slot.duration_min or 0)
        for slot in slots
    )

    lessons = lessons_for_range(db, tutor_id, start, end)
    bookings = active_bookings(db, [slot.id for slot in slots])

    states: dict[str, str] = {}
    for slot in slots:
        slot_start = as_utc(slot.starts_at)
        finish = slot_start + timedelta(minutes=slot.duration_min or 0)
        booking = bookings.get(slot.id)
        # Приоритет подписи: booking > lesson > past > free (design.md D4).
        if booking is not None:
            states[slot.id] = (
                SLOT_BOOKED if booking.status == "confirmed" else SLOT_PENDING
            )
        elif _intersects_lesson(lessons, slot_start, finish):
            states[slot.id] = SLOT_LESSON
        elif finish <= as_utc(now):
            states[slot.id] = SLOT_PAST
        else:
            states[slot.id] = SLOT_FREE
    return states


def is_free(state: str) -> bool:
    """Свободно ли окно по состоянию (только `free`)."""
    return state == SLOT_FREE
