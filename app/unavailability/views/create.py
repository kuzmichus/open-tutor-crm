"""Создание отметки недоступности из панели (design.md D8).

Ответ — сама панель (`hx-target` — `#unavailability-panel`,
`hx-swap="outerHTML"`): при успехе переотрендеренный список «Уже отмечено»
плюс `HX-Trigger: unavailability-saved`, по которому календарь
перерисовывает открытую неделю. Пустое тело не годится: список обязан
обновиться (design.md D8).

При ошибке панель возвращается со списком ошибок и присланными
значениями — введённое пользователем не теряется.

Без JS (нет `HX-Request`) ответ — 303 на календарь: форма работает и без
htmx, а отдельной страницы у панели нет.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.unavailability.services.access import require_tutor_id
from app.unavailability.services.unavailability_form import (
    panel_context,
    parse_unavailability_form,
)
from app.unavailability.services.unavailability_writer import create_mark

router = APIRouter()

PANEL_URL = "/tutor/unavailability"
CALENDAR_URL = "/tutor/calendar"


@router.post(PANEL_URL, response_class=HTMLResponse)
async def create_unavailability(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт отметку; успех — панель с событием `unavailability-saved`."""
    form = await request.form()
    data, errors = parse_unavailability_form(form)

    if not errors:
        _, errors = create_mark(db, tutor_id, data)

    if errors:
        return templates.TemplateResponse(
            request,
            "unavailability/_panel.html",
            panel_context(db, tutor_id, data=data, errors=errors),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=CALENDAR_URL, status_code=303)

    response = templates.TemplateResponse(
        request,
        "unavailability/_panel.html",
        panel_context(db, tutor_id, saved=True),
    )
    # Календарь подписан на это событие: неделя перерисовывается с сервера,
    # отметка появляется в сетке без перезагрузки страницы (design.md D8).
    response.headers["HX-Trigger"] = "unavailability-saved"
    return response
