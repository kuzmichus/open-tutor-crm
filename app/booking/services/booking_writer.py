"""Создание заявки на окно (design.md D3, спека booking-management).

Заявка создаётся в статусе «Ожидает подтверждения» и **не** создаёт ни
ученика, ни урок: подтверждение — отдельное решение педагога
(`confirmation.py`), и до него в CRM не должно появляться сущностей,
которых педагог не выбирал.

Сервис не знает про FastAPI: на вход — `Session`, окно, карточка педагога
и очищенные значения формы, на выход — бронь или список ошибок.

Проверки повторяют состояние окна (`busy.slot_states`), а не заводят
второй способ понять «занято»: свободно только `free`, остальные
состояния объясняются пользователю своим сообщением. Гонка двух
одновременных заявок ловится частичным уникальным индексом
`ux_bookings_active_slot` — вторая вставка падает на `IntegrityError` и
превращается в «время занято», а не в 500.
"""

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.booking.models.booking import Booking
from app.booking.services.booking_form import BookingParams
from app.slot.models.slot import Slot
from app.slot.services.busy import (
    SLOT_BOOKED,
    SLOT_FREE,
    SLOT_LESSON,
    SLOT_PAST,
    SLOT_PENDING,
    slot_states,
)

# Сообщения отказа. Одинаковый текст для «занято уроком» и «занято
# записью» — намеренно: публичная страница не должна раскрывать, кем
# именно занято время (спека public-booking, «Не раскрывает данные
# других учеников»).
SLOT_PRIVATE_MESSAGE = "Это окно недоступно для записи."
SLOT_PAST_MESSAGE = "Время этого окна уже прошло."
SLOT_BUSY_MESSAGE = "Это время уже занято. Выберите другое окно."

_STATE_MESSAGES = {
    SLOT_PAST: SLOT_PAST_MESSAGE,
    SLOT_PENDING: SLOT_BUSY_MESSAGE,
    SLOT_BOOKED: SLOT_BUSY_MESSAGE,
    SLOT_LESSON: SLOT_BUSY_MESSAGE,
}

def request_booking(
    db: Session,
    slot: Slot,
    params: BookingParams,
    *,
    now: datetime,
) -> tuple[Booking | None, list[str]]:
    """Создаёт заявку на свободное публичное окно; иначе — ошибка.

    `now` передаётся снаружи: «сейчас» — единый источник
    (`tutor_time.now_utc`), тесты подставляют своё значение.
    """
    if not slot.is_public:
        return None, [SLOT_PRIVATE_MESSAGE]

    state = slot_states(db, slot.tutor_id, [slot], now).get(slot.id, SLOT_FREE)
    if state != SLOT_FREE:
        return None, [_STATE_MESSAGES.get(state, SLOT_BUSY_MESSAGE)]

    booking = Booking(
        slot_id=slot.id,
        name=params.name,
        contact=params.contact,
        status="pending",
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError:
        # Параллельная заявка успела первой: частичный уникальный индекс
        # не пропустил вторую активную бронь на это окно.
        db.rollback()
        return None, [SLOT_BUSY_MESSAGE]
    return booking, []
