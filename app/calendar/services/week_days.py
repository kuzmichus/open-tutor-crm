"""Смешанная неделя календаря: реальные уроки из БД + демо-отпуск.

Уроки недели приходят из `week_lessons` (design.md D1), а заглушка отпуска
остаётся демо-источником до отдельного change'а (design.md, Non-Goals).
Оба вида живут в одном списке `ScheduleEvent` и раскладываются общим
`layout_events` — второго кода позиционирования нет (design.md D2).
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.calendar.services.demo_schedule import build_week
from app.calendar.services.schedule_day import ScheduleDay
from app.calendar.services.schedule_event import VACATION, ScheduleEvent
from app.calendar.services.week import week_lessons


def build_week_days(db: Session, tutor_id: str, monday: date) -> list[ScheduleDay]:
    """Семь дней недели: уроки репетитора из БД и демо-заглушка отпуска."""
    demo = build_week(monday)
    lessons_by_day: dict[date, list[ScheduleEvent]] = {}
    for row in week_lessons(db, tutor_id, monday):
        event = ScheduleEvent.from_lesson(
            row.lesson,
            target_name=row.target_name,
            target_id=row.target_id,
            target_color=row.target_color,
        )
        lessons_by_day.setdefault(event.day, []).append(event)

    days: list[ScheduleDay] = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        vacations = tuple(
            event for event in demo[offset].events if event.kind == VACATION
        )
        days.append(
            ScheduleDay(
                date=day,
                is_weekend=offset >= 5,
                events=tuple(lessons_by_day.get(day, ())) + vacations,
            )
        )
    return days
