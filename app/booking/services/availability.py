"""Публичные окна недели для страницы записи (design.md D8, D1).

Выборка — один `SELECT` окон недели плюс два словаря по ним (состояния
занятости и покрытие недоступности): на число окон запросов не растёт, тот
же приём, что у календаря (`slot/services/busy.py`).

Что попадает в сетку:

- **публичное окно** — педагог его опубликовал;
- **прошедшее окно** — отбрасывается: записаться в прошлое нельзя, и
  карточка «прошло» ничего не добавляет к выбору;
- **день из отметки недоступности** — отбрасывается целиком: педагог в
  отпуске/болеет, даже если окна в нём уже стояли.

Занятое окно (урок или активная бронь) **показывается**, но карточкой
«Занято»: сетка без него выглядела бы пустой и не объясняла бы, почему
время недоступно. Кем именно занято — не раскрывается: в разметку попадают
только время и состояние (design D1).

Всё считается существующими сервисами (`slot_states`,
`coverage_for_week`), а не повторной формулой: публичная страница и
календарь обязаны понимать «свободно» одинаково.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.common.services.tutor_time import to_local
from app.slot.models.slot import Slot
from app.slot.services.busy import (
    SLOT_BOOKED,
    SLOT_FREE,
    SLOT_LESSON,
    SLOT_PENDING,
    slot_states,
)
from app.slot.services.slots import week_slots
from app.unavailability.services.marks import coverage_for_week, week_days

# Состояние карточки окна на публичной странице. Отдельный закрытый список,
# а не переиспользование `slot_states`: ученику нужны только два состояния,
# а «прошло» и «приватно» до карточки не доходят вовсе.
PUBLIC_FREE = "free"
PUBLIC_BUSY = "busy"

@dataclass(frozen=True)
class PublicSlot:
    """Окно в сетке: время педагога и состояние для выбора.

    `day`/`start`/`end` — настенное время педагога: ученик видит его в
    зоне педагога, о чём страница предупреждает баннером (design D6).
    """

    slot: Slot
    day: date
    start: str
    end: str
    state: str

    @property
    def id(self) -> str:
        """id окна — то, что уходит в ссылку выбора и форму заявки."""
        return self.slot.id

    @property
    def duration_min(self) -> int:
        """Длительность окна в минутах (для подписи рядом с интервалом)."""
        return self.slot.duration_min

    @property
    def is_free(self) -> bool:
        """Можно ли выбрать это окно (только свободное)."""
        return self.state == PUBLIC_FREE

@dataclass(frozen=True)
class PublicDay:
    """Столбец сетки: дата и её окна (возможно, пустой)."""

    day: date
    slots: tuple[PublicSlot, ...]

    @property
    def is_empty(self) -> bool:
        """Нет ни одного окна — день показывает подпись «нет мест»."""
        return not self.slots

def _public_slot(slot: Slot, tutor, state: str) -> PublicSlot:
    """Окно в настенном времени педагога: дата и интервал «10:00 – 10:40»."""
    start = to_local(slot.starts_at, tutor)
    finish = start + timedelta(minutes=slot.duration_min or 0)
    return PublicSlot(
        slot=slot,
        day=start.date(),
        start=start.strftime("%H:%M"),
        end=finish.strftime("%H:%M"),
        state=state,
    )

def public_week(
    db: Session,
    tutor_id: str,
    monday: date,
    tutor,
    *,
    now: datetime,
) -> list[PublicDay]:
    """Сетка недели `monday`: семь дней, в каждом — публичные окна.

    Дни без окон остаются в списке пустыми: сетка всегда семиколоночная,
    иначе «нет мест» некуда поставить. Прошедшие окна и окна недоступных
    дней не показываются вовсе — их карточка ничего не объясняет.
    """
    slots = week_slots(db, tutor_id, monday, tutor)
    coverage = coverage_for_week(db, tutor_id, monday)
    states = slot_states(db, tutor_id, slots, now) if slots else {}

    grouped: dict[date, list[PublicSlot]] = {day: [] for day in week_days(monday)}
    for slot in slots:
        if not slot.is_public:
            continue
        state = states.get(slot.id, SLOT_FREE)
        # `slot_states` отдаёт `past` для прошедших окон; в публичной сетке
        # они не нужны — записаться в прошлое нельзя.
        if state not in (SLOT_FREE, SLOT_PENDING, SLOT_BOOKED, SLOT_LESSON):
            continue
        shown = _public_slot(
            slot,
            tutor,
            PUBLIC_FREE if state == SLOT_FREE else PUBLIC_BUSY,
        )
        if shown.day in coverage:
            continue
        # Окно, попавшее в чужую неделю из-за часового пояса, не должно
        # создавать лишний столбец: `week_days` уже задаёт семь дат.
        if shown.day not in grouped:
            continue
        grouped[shown.day].append(shown)

    return [
        PublicDay(day=day, slots=tuple(items))
        for day, items in sorted(grouped.items())
    ]

def selected_slot(
    days: list[PublicDay], slot_id: str | None
) -> PublicSlot | None:
    """Выбранное свободное окно из сетки; чужое/занятое/кривое — None.

    `slot_id` приходит из адреса, поэтому доверять ему нельзя: выбор
    засчитывается только если окно реально есть в отрисованной сетке и
    свободно (design D2).
    """
    if not slot_id:
        return None
    for day in days:
        for item in day.slots:
            if item.id == slot_id and item.is_free:
                return item
    return None

def unavailable_reason(coverage: dict, monday: date) -> str | None:
    """Причина недоступности, если вся неделя отмечена; иначе None.

    Нужна, чтобы вместо пустой сетки объяснить, почему окон нет:
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
