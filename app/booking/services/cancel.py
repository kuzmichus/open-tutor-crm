"""Отмена брони: урок и ученик остаются (design.md D10).

Отмена не удаляет созданный урок намеренно: урок мог быть уже проведён
или изменён (перенесён, оценён, получил домашнее задание). Судьбу урока
педагог решает сам, а окно после отмены автоматически покажет «Занято
уроком» — потому что занятость выводится (`busy.slot_states`), а не
хранится.

Поэтому отмена освобождает окно только в одном случае — если урока уже
нет (педагог удалил его раньше). Это не отдельная ветка кода: удалённый
урок перестаёт пересекаться, и окно становится свободным само.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.booking.models.booking import Booking
from app.booking.services.confirmation import FINAL_BOOKING_STATUSES
from app.tutor.services.clock import as_utc

CANCEL_FINAL_MESSAGE = "Бронь уже завершена: отменять нечего."
CANCEL_PENDING_MESSAGE = (
    "Бронь ещё не подтверждена: её нужно отклонить, а не отменять."
)

def cancel(db: Session, booking: Booking, *, now: datetime) -> list[str]:
    """Переводит подтверждённую бронь в «Отменена», не трогая урок."""
    if booking.status in FINAL_BOOKING_STATUSES:
        return [CANCEL_FINAL_MESSAGE]
    if booking.status != "confirmed":
        # У ожидающей брони нет урока, поэтому «отменить» нечего:
        # действие педагога называется «Отклонить».
        return [CANCEL_PENDING_MESSAGE]

    booking.status = "cancelled"
    booking.decided_at = as_utc(now)
    db.commit()
    return []
