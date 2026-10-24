"""Диалог окна: параметры, состояние и действия (спека calendar).

`GET /tutor/slots/{slot_id}` открывает диалог существующего окна в
контейнере `#modal`. Клик по карточке окна ведёт сюда, а не в форму
урока (спека calendar, «Окно не открывает форму урока»).

Чужое или несуществующее окно — 404, как в `get_owned_slot`: существование
чужой записи не раскрывается (спека slot-management, «Изоляция по
репетитору»).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.slot.services.access import get_owned_slot, require_tutor_id
from app.slot.services.dialog_context import dialog_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

SLOTS_URL = "/tutor/slots"


@router.get(f"{SLOTS_URL}/{{slot_id}}", response_class=HTMLResponse)
def slot_dialog(
    slot_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Диалог окна этого репетитора; чужое окно — 404."""
    slot = get_owned_slot(db, slot_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "slot/_dialog.html",
        dialog_context(db, tutor, slot=slot),
    )
