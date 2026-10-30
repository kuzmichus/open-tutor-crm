"""Список броней репетитора для страницы «Брони и заявки».

У брони нет своей колонки `tutor_id` (design.md D3): владелец выводится
из окна, поэтому список выбирается одним `SELECT` с `JOIN slots` — как
`get_owned_booking`, только на все строки сразу, без N+1 на карточку.

Список делится на два блока по смыслу решения, а не просто по статусу:

- «Ожидают подтверждения» — ожидающие заявки, ближайшие по времени окна
  первыми: педагог разбирает их в порядке занятия;
- «История» — всё, у чего решение есть или оно завершающее, новые сверху
  по моменту решения. Подтверждённая бронь попадает и сюда: до занятия
  её ещё можно отменить.

Подписи и даты для шаблона собирает `presentation.py`; здесь — только
выборка, группировка и решение «что с бронью ещё можно сделать».
`pending_count` — та же выборка, агрегированная на сервере: счётчик
необработанных заявок в сайдбаре.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.booking.models.booking import Booking
from app.booking.services.presentation import (
    booking_status_label,
    decided_day,
    day_full,
    day_time,
)
from app.common.services.tutor_time import to_local
from app.slot.models.slot import Slot
from app.slot.services.busy import slot_end
from app.tutor.services.clock import as_utc


def _row(booking: Booking, slot: Slot, tutor, *, now: datetime) -> dict:
    """Карточка/строка брони для шаблона: объекты и готовые подписи."""
    start = to_local(slot.starts_at, tutor)
    end = start + timedelta(minutes=slot.duration_min or 0)
    return {
        "booking": booking,
        "slot": slot,
        # «17:15 – 17:55» — интервал окна в зоне педагога. Окончание
        # считается в локальном времени: интервал через переход на летнее
        # время остаётся верным (design D3, как `slot_span`).
        "span": f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')}",
        "day_full": day_full(slot.starts_at, tutor),
        "day_time": day_time(slot.starts_at, tutor),
        "decided": decided_day(booking, tutor),
        "status_label": booking_status_label(booking.status),
        # Отменить можно только подтверждённую бронь на будущее (design D10):
        # прошедшее занятие отменять поздно, а ожидающую — отклоняют.
        "cancellable": booking.status == "confirmed"
        and slot_end(slot) > as_utc(now),
    }


def tutor_bookings(
    db: Session, tutor_id: str, tutor, *, now: datetime
) -> dict:
    """Контекст списка броней: `pending` и `history` для `booking/_list.html`."""
    rows = db.execute(
        select(Booking, Slot)
        .join(Slot, Slot.id == Booking.slot_id)
        .where(Slot.tutor_id == tutor_id)
    ).all()

    pending: list[dict] = []
    history: list[dict] = []
    for booking, slot in rows:
        row = _row(booking, slot, tutor, now=now)
        if booking.status == "pending":
            pending.append(row)
        else:
            history.append(row)

    # Ожидающие — по времени окна (ближайшее сверху); история — по моменту
    # решения, у ожидающих этого момента нет, но они в историю не попадают.
    pending.sort(key=lambda row: as_utc(row["slot"].starts_at))
    history.sort(
        key=lambda row: as_utc(row["booking"].decided_at
                               or row["booking"].created_at),
        reverse=True,
    )
    return {"pending": pending, "history": history}


def pending_count(db: Session, tutor_id: str) -> int:
    """Число необработанных заявок — счётчик в сайдбаре (спека booking-management).

    Тот же JOIN через `slots`, что у `tutor_bookings`: владелец брони
    выводится из окна, поэтому чужие заявки в счётчик не попадают.
    Агрегат на сервере, а не `len(pending)`: счётчику не нужны карточки
    и подписи списка.
    """
    return (
        db.scalar(
            select(func.count())
            .select_from(Booking)
            .join(Slot, Slot.id == Booking.slot_id)
            .where(Slot.tutor_id == tutor_id, Booking.status == "pending")
        )
        or 0
    )
