"""Доступные для записи окна недели на публичной странице (design.md D8).

Выборка — один `SELECT` окон недели плюс два словаря по ним (состояния
занятости и покрытие недоступности): на число окон запросов не растёт, тот
же приём, что у календаря (`slot/services/busy.py`).

Что отсеивается и почему:

- **приватное окно** — педагог не публиковал его ученику;
- **прошедшее окно** — записаться в прошлое нельзя;
- **занятое уроком или активной бронью** — время уже занято;
- **день из отметки недоступности** — педагог в отпуске/болеет.

Всё это считается существующими сервисами (`slot_states`,
`coverage_for_week`), а не повторной формулой: публичная страница и
календарь обязаны понимать «свободно» одинаково.

В разметку попадают только дата, время и длительность. Ни имён учеников,
ни заметок, ни контактов — это требование спеки public-booking, и его
проверяет тест на отсутствие подстрок.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.common.services.tutor_time import to_local
from app.slot.models.slot import Slot
from app.slot.services.busy import SLOT_FREE, slot_states
from app.slot.services.slots import week_slots
from app.unavailability.services.marks import coverage_for_week, week_days

@dataclass(frozen=True)
class PublicSlot:
    """Свободное окно в виде, пригодном для показа ученику.

    `day`/`start`/`end` — настенное время педагога: ученик видит его в
    зоне педагога, о чём страница предупреждает подписью (design D8).
    """

    slot: Slot
    day: date
    start: str
    end: str

    @property
    def id(self) -> str:
        """id окна — то, что уходит в форму заявки."""
        return self.slot.id

    @property
    def duration_min(self) -> int:
        """Длительность окна в минутах (для подписи рядом с интервалом)."""
        return self.slot.duration_min

def _public_slot(slot: Slot, tutor) -> PublicSlot:
    """Окно в настенном времени педагога: дата и интервал «10:00 – 10:40»."""
    start = to_local(slot.starts_at, tutor)
    finish = start + timedelta(minutes=slot.duration_min or 0)
    return PublicSlot(
        slot=slot,
        day=start.date(),
        start=start.strftime("%H:%M"),
        end=finish.strftime("%H:%M"),
    )

def free_slots(
    db: Session,
    tutor_id: str,
    monday: date,
    tutor,
    *,
    now: datetime,
) -> list[PublicSlot]:
    """Свободные публичные окна недели `monday`, по времени начала.

    Недоступный день отсекается целиком: даже если окно в нём уже стояло
    (педагог отметил отпуск после создания пачки), ученику оно не
    показывается — спека slot-management, «Отпуск не удаляет окна».
    """
    slots = week_slots(db, tutor_id, monday, tutor)
    if not slots:
        return []

    coverage = coverage_for_week(db, tutor_id, monday)
    states = slot_states(db, tutor_id, slots, now)

    free: list[PublicSlot] = []
    for slot in slots:
        if not slot.is_public:
            continue
        if states.get(slot.id) != SLOT_FREE:
            continue
        shown = _public_slot(slot, tutor)
        if shown.day in coverage:
            continue
        free.append(shown)
    return free

def slots_by_day(slots: list[PublicSlot]) -> list[tuple[date, list[PublicSlot]]]:
    """Группировка по дням для шаблона: [(дата, окна)] в порядке недели.

    Дни без свободных окон в список не попадают — шаблон показывает только
    то, что можно выбрать.
    """
    grouped: dict[date, list[PublicSlot]] = {}
    for slot in slots:
        grouped.setdefault(slot.day, []).append(slot)
    return sorted(grouped.items(), key=lambda item: item[0])

def unavailable_reason(coverage: dict, monday: date) -> str | None:
    """Причина недоступности, если вся неделя отмечена; иначе None.

    Нужна, чтобы вместо пустого списка окон объяснить, почему их нет:
    «Педагог недоступен: Отпуск» (спека public-booking, «Неделя в
    отпуске»).
    """
    if not coverage:
        return None
    if all(day in coverage for day in week_days(monday)):
        # Причина берётся у первого дня недели: неделя целиком покрыта,
        # значит причина у всех дней одна и та же (или главная совпадает).
        return coverage[monday].reason_label
    return None
