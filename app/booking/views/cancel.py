"""Отмена подтверждённой брони из диалога окна (спека booking-management).

`POST /tutor/bookings/{booking_id}/cancel` — действие педагога: бронь
переходит в «Отменена», созданный урок и ученик остаются
(`booking/services/cancel.py`, design D10). Окно после отмены покажет
«Занято уроком», пока педагог не удалит урок сам.

Ответ при ошибке — диалог окна с сообщением (бронь уже завершена или ещё
не подтверждена). Успех — пустое тело и `HX-Trigger: slot-saved`: неделя
перерисовывается с сервера.

Чужая или несуществующая бронь — 404 (существование не раскрывается).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.booking.services.access import get_owned_booking, require_tutor_id
from app.booking.services.cancel import cancel
from app.common.responses import dialog_closed
from app.common.services.tutor_time import now_utc
from app.database import get_db
from app.slot.models.slot import Slot
from app.slot.services.dialog_context import dialog_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

BOOKINGS_URL = "/tutor/bookings"
CALENDAR_URL = "/tutor/calendar"

@router.post(f"{BOOKINGS_URL}/{{booking_id}}/cancel", response_class=HTMLResponse)
def cancel_booking(
    booking_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Отменяет подтверждённую бронь, не трогая урок и ученика."""
    booking = get_owned_booking(db, booking_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    slot = db.get(Slot, booking.slot_id)

    errors = cancel(db, booking, now=now_utc())
    if errors:
        return templates.TemplateResponse(
            request,
            "slot/_dialog.html",
            dialog_context(db, tutor, slot=slot, errors=errors),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=CALENDAR_URL, status_code=303)
    return dialog_closed()
