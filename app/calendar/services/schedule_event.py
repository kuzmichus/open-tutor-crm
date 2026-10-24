"""Событие календаря: урок или окно для записи из БД.

Заглушка отпуска удалена вместе с демо-слоем: недоступность больше не
событие сетки, а отметка на дне (`ScheduleDay.unavailable`) — она не
занимает время и не участвует в раскладке карточек (design.md D7).

Поля события несут два кадра времени (design D4): `starts_at`/`ends_at` —
aware UTC, источник истины для сравнения с «сейчас», а `day`/`start`/`end`
— локальные значения педагога, по которым событие раскладывается в сетке.

Признак вида (`kind`) появился вместе с окнами (design.md D5): раньше
демо-слот отличался от урока пустым `lesson_id`, но после удаления демо
этого признака не хватает — окно и урок оба приходят из БД, и «пустой id»
перестал что-либо означать. Теперь вид задан явно: `EVENT_LESSON` или
`EVENT_SLOT`.

Раскладка пересечений не меняется: `build_week_days` собирает уроки и окна
в один список `events`, поэтому `layout_events` раскладывает окно с уроком
тем же кодом, что два урока (design D5).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.common.services.tutor_time import to_local
from app.tutor.services.clock import as_utc

# Виды событий сетки. Строки, а не Enum: значения уходят в разметку
# (`data-event-kind`) и в тесты, где сравнение со строкой читается проще.
EVENT_LESSON = "lesson"
EVENT_SLOT = "slot"

@dataclass(frozen=True)
class ScheduleEvent:
    """Одно событие внутри дня недели: урок или окно для записи.

    Несёт `lesson_id`/`status`/`is_completed`/`target_id` для урока и
    `slot_id`/`slot_state` для окна: по ним карточка отличается визуально и
    служит адресом своей формы — урока или диалога окна (design.md D2/D5).
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
    # Вид события: урок или окно. По умолчанию урок — так все прежние
    # вызовы (`from_lesson`) остаются валидными без правки.
    kind: str = EVENT_LESSON
    # Окно: id для диалога и вычисленное состояние занятости (design D4).
    slot_id: str = ""
    slot_state: str = ""
    duration_min: int = 0

    @property
    def is_slot(self) -> bool:
        """Окно ли это (карточка окна, а не урока)."""
        return self.kind == EVENT_SLOT

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
            kind=EVENT_LESSON,
            duration_min=lesson.duration_min or 0,
        )

    @classmethod
    def from_slot(cls, slot, *, slot_state: str, tutor) -> "ScheduleEvent":
        """Событие-окно: интервал, состояние занятости и id для диалога.

        Цвет окна не берётся из палитры целей: окно — не ученик и не
        группа, у него собственный токен `--cal-slot-accent` (спека
        calendar, «Карточка окна визуально отличается от урока»).
        `student`/`price` намеренно пустые — окно не раскрывает, кто занял
        время, и не имеет цены.
        """
        starts_at = as_utc(slot.starts_at)
        finish = starts_at + timedelta(minutes=slot.duration_min or 0)
        local_start = to_local(starts_at, tutor)
        local_end = to_local(finish, tutor)
        end = local_end.time() if local_end.date() == local_start.date() else time(23, 59)
        return cls(
            starts_at=starts_at,
            ends_at=finish,
            day=local_start.date(),
            start=local_start.time(),
            end=end,
            kind=EVENT_SLOT,
            slot_id=slot.id,
            slot_state=slot_state,
            duration_min=slot.duration_min or 0,
        )
