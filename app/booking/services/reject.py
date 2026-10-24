"""Отклонение заявки: окно снова свободно (design.md D10).

Отклонение не создаёт ни ученика, ни урок — заявка была только намерением.
Окно при этом автоматически становится свободным: занятость выводится
пересечением с активными бронями (`busy.slot_states`), а не хранится, и
перевод брони в завершающий статус убирает её из активных.

Завершающие брони не меняются (спека booking-management): повторное
действие отклоняется сообщением, а не «перезаписывает» историю решения.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.booking.models.booking import Booking
from app.booking.services.confirmation import FINAL_BOOKING_STATUSES
from app.tutor.services.clock import as_utc

REJECT_FINAL_MESSAGE = "Бронь уже завершена: отклонять нечего."
REJECT_CONFIRMED_MESSAGE = (
    "Бронь уже подтверждена: чтобы освободить окно, отмените её."
)

def reject(db: Session, booking: Booking, *, now: datetime) -> list[str]:
    """Переводит ожидающую бронь в «Отклонена»; урок и ученик не создаются."""
    if booking.status in FINAL_BOOKING_STATUSES:
        return [REJECT_FINAL_MESSAGE]
    if booking.status == "confirmed":
        # Подтверждённую бронь уже нельзя «отклонить»: за ней стоит урок,
        # и у пользователя есть отдельное действие «Отменить».
        return [REJECT_CONFIRMED_MESSAGE]

    booking.status = "rejected"
    booking.decided_at = as_utc(now)
    db.commit()
    return []
