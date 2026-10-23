"""Дни недели календаря: реальные уроки из БД и отметки недоступности.

Уроки недели приходят из `week_lessons` (design.md D1), отметки — из
`unavailability.marks.coverage_for_week` (design.md D3): один запрос на
неделю, дальше покрытие разворачивается в Python по семи датам. Демо-отпуск
удалён — недоступность хранится в БД и действует по реальным датам.

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
from app.unavailability.services.marks import coverage_for_week


def build_week_days(db: Session, tutor_id: str, monday: date, tutor) -> list[ScheduleDay]:
    """Семь дней недели: уроки репетитора из БД и отметки недоступности.

    `tutor` — карточка репетитора: её зона задаёт границы окна недели и
    локальные `day`/`start`/`end` каждого события. Перевод в зону делает
    `ScheduleEvent.from_lesson` (design D4), поэтому здесь события
    раскладываются по дням уже по локальной дате педагога.
    """
    coverage = coverage_for_week(db, tutor_id, monday)

    lessons_by_day: dict[date, list[ScheduleEvent]] = {}
    for row in week_lessons(db, tutor_id, monday, tutor):
        event = ScheduleEvent.from_lesson(
            row.lesson,
            target_name=row.target_name,
            target_id=row.target_id,
            target_color=row.target_color,
            tutor=tutor,
        )
        lessons_by_day.setdefault(event.day, []).append(event)

    days: list[ScheduleDay] = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        days.append(
            ScheduleDay(
                date=day,
                events=tuple(lessons_by_day.get(day, ())),
                unavailable=coverage.get(day),
            )
        )
    return days
