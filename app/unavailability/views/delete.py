"""Снятие отметки недоступности (design.md D10).

Подтверждение — на клиенте (двухшаговое, как удаление группы): первый
клик по «Снять» переводит кнопку в «Точно снять?», второй отправляет POST.
Ответ — панель с обновлённым списком и событием `unavailability-saved`:
неделя перерисовывается, штриховка снимается.

Чужая или несуществующая отметка отвечает как отсутствующая (404).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.unavailability.services.access import (
    get_owned_unavailability,
    require_tutor_id,
)
from app.unavailability.services.unavailability_form import panel_context
from app.unavailability.services.unavailability_writer import delete_mark

router = APIRouter()

PANEL_URL = "/tutor/unavailability"
CALENDAR_URL = "/tutor/calendar"


@router.post(f"{PANEL_URL}/{{mark_id}}/delete", response_class=HTMLResponse)
def delete_unavailability(
    mark_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Снимает отметку; чужую отметку не раскрывает (404)."""
    mark = get_owned_unavailability(db, mark_id, tutor_id)
    delete_mark(db, mark)

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=CALENDAR_URL, status_code=303)

    response = templates.TemplateResponse(
        request,
        "unavailability/_panel.html",
        panel_context(db, tutor_id, saved=True),
    )
    response.headers["HX-Trigger"] = "unavailability-saved"
    return response
