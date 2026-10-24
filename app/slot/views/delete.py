"""Удаление окна (design D11).

Окно с активной бронью не удаляется: бронь каскадна к окну, поэтому
«удалить» молча уничтожило бы заявку человека. Отказ возвращается
диалогом с объяснением — сначала бронь отклоняется или отменяется.

Уроки удаление окна не трогает: окно и урок связаны только временем,
а не ссылкой (спека slot-management, «Удаление окна не трогает урок»).

Чужое или несуществующее окно — 404 (существование не раскрывается).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed
from app.database import get_db
from app.slot.services.access import get_owned_slot, require_tutor_id
from app.slot.services.dialog_context import dialog_context
from app.slot.services.slot_writer import delete_slot
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

SLOTS_URL = "/tutor/slots"
CALENDAR_URL = "/tutor/calendar"


@router.post(f"{SLOTS_URL}/{{slot_id}}/delete", response_class=HTMLResponse)
def delete_slot_view(
    slot_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Удаляет окно без активной брони; чужое окно — 404."""
    slot = get_owned_slot(db, slot_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)

    errors = delete_slot(db, slot)
    if errors:
        # Окно осталось на месте: диалог возвращается с причиной отказа.
        return templates.TemplateResponse(
            request,
            "slot/_dialog.html",
            dialog_context(db, tutor, slot=slot, errors=errors),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=CALENDAR_URL, status_code=303)
    return dialog_closed()
