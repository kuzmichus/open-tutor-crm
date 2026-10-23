"""Событие календаря: урок репетитора из БД.

Заглушка отпуска удалена вместе с демо-слоем: недоступность больше не
событие сетки, а отметка на дне (`ScheduleDay.unavailable`) — она не
занимает время и не участвует в раскладке карточек (design.md D7).

Поля события несут два кадра времени (design D4): `starts_at`/`ends_at` —
aware UTC, источник истины для сравнения с «сейчас», а `day`/`start`/`end`
— локальные значения педагога, по которым событие раскладывается в сетке.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.common.services.tutor_time import to_local
from app.tutor.services.clock import as_utc


@dataclass(frozen=True)
class ScheduleEvent:
    """Одно событие внутри дня недели: реальный урок репетитора.

    Несёт `lesson_id`/`status`/`is_completed`/`target_id`: по непустому
    `lesson_id` карточка отличается от клиентского демо-слота и служит
    адресом формы редактирования (design.md D2).
    """

    starts_at: datetime
    ends_at: datetime
    day: date
    start: time
    end: time
    student: str = ""
    price: int = 0
    color: str = ""
    is_group: bool = False
    lesson_id: str = ""
    status: str = ""
    is_completed: bool = False
    target_id: str = ""

    @classmethod
    def from_lesson(
        cls,
        lesson,
        *,
        target_name: str,
        target_id: str,
        target_color: str,
        tutor,
    ) -> "ScheduleEvent":
        """Событие из строки БД: цель, цена, цвет и статус урока (D2).

        `starts_at` хранится в UTC — нормализуем его в aware UTC (`as_utc`,
        SQLite теряет tzinfo), а локальные `day`/`start`/`end` считаем в
        зоне педагога: раскладка сетки идёт по настенному времени (D3).
        """
        starts_at = as_utc(lesson.starts_at)
        finish = starts_at + timedelta(minutes=lesson.duration_min or 0)
        local_start = to_local(starts_at, tutor)
        local_end = to_local(finish, tutor)
        # Урок через полночь не выходит за нижнюю границу сетки: конец
        # прижимается к 23:59, иначе интервал «14:00 – 00:30» стал бы
        # отрицательным по минутам суток.
        end = local_end.time() if local_end.date() == local_start.date() else time(23, 59)
        return cls(
            starts_at=starts_at,
            ends_at=finish,
            day=local_start.date(),
            start=local_start.time(),
            end=end,
            student=target_name,
            price=lesson.price or 0,
            color=target_color,
            is_group=lesson.group_id is not None,
            lesson_id=lesson.id,
            status=lesson.status,
            is_completed=lesson.status == "completed",
            target_id=target_id,
        )
