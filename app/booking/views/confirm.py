"""Подтверждение брони из диалога окна (спека booking-management).

`POST /tutor/bookings/{booking_id}/confirm` — действие педагога: находит
или создаёт ученика, создаёт урок по времени окна и связывает бронь
(`booking/services/confirmation.py`, design D9).

Форма может прислать `student_id` (выбор при нескольких совпадениях) и
`kind` (признак создаваемого ученика). Оба необязательны: требование
возникает только в своём исходе поиска, поэтому «пусто» — это нормальное
значение, а не ошибка разбора.

Ответ при ошибке — диалог окна с сообщением: пользователь остаётся там же,
где нажимал кнопку, и видит, что именно поправить (признак не выбран,
время занято, нужно выбрать ученика). Успех — пустое тело и
`HX-Trigger: slot-saved`: неделя перерисовывается с сервера, карточка окна
становится «Занято записью».

Чужая или несуществующая бронь — 404 (существование не раскрывается).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.booking.services.access import get_owned_booking, require_tutor_id
from app.booking.services.confirmation import confirm
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

def _choice(form) -> str:
    """Выбранный ученик из формы; пустое значение — «не выбран»."""
    value = form.get("student_id")
    return value.strip() if isinstance(value, str) else ""

def _kind(form) -> str:
    """Признак нового ученика из формы; недопустимое значение — пусто."""
    value = form.get("kind")
    return value.strip() if isinstance(value, str) else ""

@router.post(f"{BOOKINGS_URL}/{{booking_id}}/confirm", response_class=HTMLResponse)
async def confirm_booking(
    booking_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Подтверждает бронь; при отказе возвращает диалог с причиной."""
    booking = get_owned_booking(db, booking_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    slot = db.get(Slot, booking.slot_id)
    form = await request.form()

    _, errors = confirm(
        db,
        booking,
        tutor,
        chosen_student_id=_choice(form) or None,
        kind=_kind(form) or None,
        now=now_utc(),
    )

    if errors:
        return templates.TemplateResponse(
            request,
            "slot/_dialog.html",
            dialog_context(db, tutor, slot=slot, errors=errors),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=CALENDAR_URL, status_code=303)
    return dialog_closed()
