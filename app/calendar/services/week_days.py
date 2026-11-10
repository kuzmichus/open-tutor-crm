"""Дни недели календаря: уроки, окна для записи и отметки недоступности.

Уроки недели приходят из `week_lessons` (design.md D1), окна — из
`slot/services/slots.py::week_slots`, отметки — из
`unavailability.marks.coverage_for_week` (design.md D3): один запрос на
неделю, дальше покрытие разворачивается в Python по семи датам.

Уроки и окна лежат в одном списке `day.events` (design D5): `layout_events`
раскладывает окно с уроком тем же кодом, что два урока, поэтому окно 14:00
и урок 14:00 не рисуются друг на друге. Состояние окна считается
`busy.slot_states` — пересечением с уже загруженными уроками и активными
бронями, без хранения (design D4).

Выходных «по календарю» нет: суббота и воскресенье ничем не выделяются,
пока репетитор не занёс отметку в таблицу `tutor_unavailability`. Раньше
здесь был флаг `is_weekend = offset >= 5`, из-за которого сб/вс всегда
рисовались как выходные — это противоречило правилу «единственный источник
выходных — отметки пользователя».
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.calendar.services.schedule_day import ScheduleDay
from app.calendar.services.schedule_event import ScheduleEvent
from app.calendar.services.week import week_lessons
from app.common.services.tutor_time import now_utc
from app.homework.services.by_lesson import homework_by_lesson
from app.slot.services.busy import slot_states
from app.slot.services.slots import week_slots
from app.unavailability.services.marks import coverage_for_week


def build_week_days(db: Session, tutor_id: str, monday: date, tutor) -> list[ScheduleDay]:
    """Семь дней недели: уроки, окна репетитора и отметки недоступности.

    `tutor` — карточка репетитора: её зона задаёт границы окна недели и
    локальные `day`/`start`/`end` каждого события. Перевод в зону делает
    `ScheduleEvent.from_lesson`/`from_slot` (design D4), поэтому здесь
    события раскладываются по дням уже по локальной дате педагога.
    """
    coverage = coverage_for_week(db, tutor_id, monday)

    # Статусы ДЗ — один SELECT на всю неделю (правило AGENTS.md 9): карточка
    # берёт статус из карты, а не ходит в БД на каждый урок.
    rows = week_lessons(db, tutor_id, monday, tutor)
    homework = homework_by_lesson(db, [row.lesson.id for row in rows])

    events_by_day: dict[date, list[ScheduleEvent]] = {}
    for row in rows:
        event = ScheduleEvent.from_lesson(
            row.lesson,
            target_name=row.target_name,
            target_id=row.target_id,
            target_color=row.target_color,
            tutor=tutor,
            # Цена посчитана в недельной выборке: у группового урока это
            # стоимость всей группы (одно правило с финансами).
            price=row.price,
            homework_status=homework.get(row.lesson.id, ""),
        )
        events_by_day.setdefault(event.day, []).append(event)

    # Состояние окна зависит от уроков и броней, а не только от самого окна,
    # поэтому считается пачкой на всю неделю: два запроса независимо от
    # числа окон (design D4, Risks).
    slots = week_slots(db, tutor_id, monday, tutor)
    states = slot_states(db, tutor_id, slots, now_utc())
    for slot in slots:
        event = ScheduleEvent.from_slot(
            slot,
            slot_state=states.get(slot.id, ""),
            tutor=tutor,
        )
        events_by_day.setdefault(event.day, []).append(event)

    days: list[ScheduleDay] = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        days.append(
            ScheduleDay(
                date=day,
                events=tuple(events_by_day.get(day, ())),
                unavailable=coverage.get(day),
            )
        )
    return days
