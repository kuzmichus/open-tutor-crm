"""Событие demo-расписания: урок или заглушка отпуска."""

from dataclasses import dataclass
from datetime import date, time

# Виды событий календаря. `vacation` — блок-заглушка «Отпуск»: визуально
# отличается от урока и не открывает форму создания (см. спеку).
LESSON = "lesson"
VACATION = "vacation"


@dataclass(frozen=True)
class ScheduleEvent:
    """Одно событие внутри дня демо-недели.

    Для урока заполнены `student`/`price`/`color`/`is_group`; для отпуска
    они пустые — событие занимает весь день.
    """

    day: date
    start: time
    end: time
    kind: str = LESSON
    student: str = ""
    price: int = 0
    color: str = ""
    is_group: bool = False

    @property
    def is_lesson(self) -> bool:
        """Урок, а не заглушка (отпуск)."""
        return self.kind == LESSON
