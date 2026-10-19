"""День недели демо-расписания со списком событий."""

from dataclasses import dataclass
from datetime import date

from app.calendar.services.schedule_event import ScheduleEvent


@dataclass(frozen=True)
class ScheduleDay:
    """Один столбец сетки календаря: дата, выходной, события дня."""

    date: date
    is_weekend: bool
    events: tuple[ScheduleEvent, ...] = ()

    @property
    def lessons(self) -> tuple[ScheduleEvent, ...]:
        """Только уроки дня (заглушки «Отпуск» не считаются)."""
        return tuple(event for event in self.events if event.is_lesson)
