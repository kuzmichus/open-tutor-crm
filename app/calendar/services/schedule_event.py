"""Событие календаря: реальный урок из БД или заглушка отпуска."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

# Виды событий календаря. `vacation` — блок-заглушка «Отпуск»: визуально
# отличается от урока и не открывает форму создания (см. спеку).
LESSON = "lesson"
VACATION = "vacation"


@dataclass(frozen=True)
class ScheduleEvent:
    """Одно событие внутри дня недели.

    Для урока заполнены `student`/`price`/`color`/`is_group`; для отпуска
    они пустые — событие занимает весь день. Урок из БД дополнительно несёт
    `lesson_id`/`status`/`is_completed`/`target_id`: по непустому `lesson_id`
    карточка отличается от демо-события (design.md D2).
    """

    day: date
    start: time
    end: time
    kind: str = LESSON
    student: str = ""
    price: int = 0
    color: str = ""
    is_group: bool = False
    # Поля реального урока; у демо-событий пустые.
    lesson_id: str = ""
    status: str = ""
    is_completed: bool = False
    target_id: str = ""

    @property
    def is_lesson(self) -> bool:
        """Урок, а не заглушка (отпуск)."""
        return self.kind == LESSON

    @classmethod
    def from_lesson(
        cls, lesson, *, target_name: str, target_id: str, target_color: str
    ) -> "ScheduleEvent":
        """Событие из строки БД: цель, цена, цвет и статус урока (D2).

        Начало и конец — наивное время `starts_at`, как везде в проекте
        (конвертация часового пояса отложена отдельным change'ом).
        """
        start = lesson.starts_at
        finish = start + timedelta(minutes=lesson.duration_min or 0)
        # Урок через полночь не выходит за нижнюю границу сетки: конец
        # прижимается к 23:59, иначе интервал «14:00 – 00:30» стал бы
        # отрицательным по минутам суток.
        end = finish.time() if finish.date() == start.date() else time(23, 59)
        return cls(
            day=start.date(),
            start=start.time(),
            end=end,
            kind=LESSON,
            student=target_name,
            price=lesson.price or 0,
            color=target_color,
            is_group=lesson.group_id is not None,
            lesson_id=lesson.id,
            status=lesson.status,
            is_completed=lesson.status == "completed",
            target_id=target_id,
        )
