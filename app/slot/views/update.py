"""Изменение окна: начало, длительность и публичность (design D11).

`POST /tutor/slots/{slot_id}` меняет поля окна. Бронь не трогается — она
ссылается на окно по id и «едет» вместе с ним (спека slot-management,
«Перенос окна с бронью»). Пересечение на новом времени отклоняет перенос,
окно остаётся на прежнем месте.

Успех — пустое тело и `HX-Trigger: slot-saved`: неделя перерисовывается с
сервера. Ошибка — диалог с сообщением и присланными значениями.

Чужое или несуществующее окно — 404 (существование не раскрывается).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed
from app.common.responses import is_htmx
from app.database import get_db
from app.slot.services.access import get_owned_slot, require_tutor_id
from app.slot.services.dialog_context import dialog_context
from app.slot.services.slot_form import parse_slot_form, slot_form_values
from app.slot.services.slot_writer import move_slot
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

SLOTS_URL = "/tutor/slots"
CALENDAR_URL = "/tutor/calendar"


@router.post(f"{SLOTS_URL}/{{slot_id}}", response_class=HTMLResponse)
async def update_slot_view(
    slot_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Применяет форму к окну; чужое окно не раскрывается (404)."""
    slot = get_owned_slot(db, slot_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    form = await request.form()
    params, errors = parse_slot_form(form)

    if not errors:
        errors = move_slot(db, slot, tutor, params)

    if errors:
        return templates.TemplateResponse(
            request,
            "slot/_dialog.html",
            dialog_context(
                db,
                tutor,
                slot=slot,
                data=slot_form_values(form),
                errors=errors,
            ),
        )

    if not is_htmx(request):
        return RedirectResponse(url=CALENDAR_URL, status_code=303)
    return dialog_closed()
