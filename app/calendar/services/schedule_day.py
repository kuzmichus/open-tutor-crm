"""День недели календаря: дата, события и отметка недоступности."""

from dataclasses import dataclass
from datetime import date

from app.calendar.services.schedule_event import ScheduleEvent
from app.unavailability.services.marks import DayMark


@dataclass(frozen=True)
class ScheduleDay:
    """Один столбец сетки календаря: дата, события, недоступность.

    Выходных «по календарю» здесь нет: единственный источник выходных —
    отметки в таблице `tutor_unavailability` (спека calendar, «Выходные
    задаёт репетитор отметками»). Суббота и воскресенье отличаются от
    будней только подписью дня недели — пока репетитор не отметил их сам.

    `unavailable` — отметка недоступности этого дня (`None` — день доступен).
    Отдельное поле, а не событие: отметка не занимает время в сетке, она
    красит тело дня и подписывается в шапке (спека calendar, «Отмеченный
    день виден в сетке»).
    """

    date: date
    events: tuple[ScheduleEvent, ...] = ()
    unavailable: DayMark | None = None
