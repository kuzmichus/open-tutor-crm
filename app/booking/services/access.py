"""Доступ к брони: `get_owned_booking` через окно.

У брони нет своего `tutor_id` (design.md D3): владелец выводится из окна,
как владелец урока выводится из цели. Поэтому доступ проверяется одним
`SELECT` с `JOIN slots` по `id` брони и `tutor_id` окна — без второго
запроса на проверку владельца.

Чужая и несуществующая бронь неразличимы: 404, а не 403 — существование
чужой заявки не раскрывается (спека booking-management, «Действия с
бронью доступны только владельцу»).

Ри-экспорт `require_tutor_id`/`LoginRequired` — по правилу AGENTS.md:
вьюхи модуля не зависят от `common` напрямую.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.booking.models.booking import Booking
from app.common.access import LOGIN_URL, LoginRequired, require_tutor_id
from app.slot.models.slot import Slot

__all__ = ["LOGIN_URL", "LoginRequired", "get_owned_booking", "require_tutor_id"]

def get_owned_booking(db: Session, booking_id: str, tutor_id: str) -> Booking:
    """Бронь окна этого репетитора либо 404."""
    booking = db.scalars(
        select(Booking)
        .join(Slot, Slot.id == Booking.slot_id)
        .where(Booking.id == booking_id, Slot.tutor_id == tutor_id)
    ).one_or_none()
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return booking
