"""Выборка окон репетитора: неделя и произвольный интервал (design.md D2).

Границы недели считаются в зоне педагога (`local_week_bounds`): прибавление
`timedelta` к UTC-значению сломало бы неделю с переводом часов — тот же
принцип, что в `calendar/services/week.py`.

Выборки не делают запросов на каждую запись: неделя — один `SELECT`, а
состояние занятости считается отдельным сервисом (`busy.py`) по уже
загруженным строкам.
"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_week_bounds
from app.slot.models.slot import Slot


def slots_between(
    db: Session, tutor_id: str, start: datetime, end: datetime
) -> list[Slot]:
    """Окна этого репетитора, начинающиеся в `[start, end)`.

    Окно недели задаётся по началу (как у уроков, design D1): окно,
    начавшееся в воскресенье, в следующую неделю не попадает.
    """
    stmt = (
        select(Slot)
        .where(
            Slot.tutor_id == tutor_id,
            Slot.starts_at >= start,
            Slot.starts_at < end,
        )
        .order_by(Slot.starts_at, Slot.id)
    )
    return list(db.scalars(stmt))


def week_slots(db: Session, tutor_id: str, monday: date, tutor) -> list[Slot]:
    """Окна недели `monday` этого репетитора, по времени начала.

    `tutor` — карточка репетитора: её зона задаёт границы недели
    (aware UTC), а `starts_at` хранится в UTC (спека tutor-timezone).
    """
    start, end = local_week_bounds(monday, tutor)
    return slots_between(db, tutor_id, start, end)
