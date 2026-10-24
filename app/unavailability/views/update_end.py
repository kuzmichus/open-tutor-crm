"""«Изменить срок» отметки: только последний день (design.md D9).

Отдельный эндпоинт, а не полная форма правки: причина и первый день
отметки не меняются, а «снять и поставить заново» — ровно то, чего
просили избежать. Для «Постоянного выходного» тем же способом правится
«Действует по».

Пустое значение — бессрочно (период) / без ограничения (выходной).
Ответ — панель с обновлённым списком и событием `unavailability-saved`.
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
from app.unavailability.services.unavailability_form import (
    panel_context,
    parse_end_form,
)
from app.unavailability.services.unavailability_writer import change_end

router = APIRouter()

PANEL_URL = "/tutor/unavailability"
CALENDAR_URL = "/tutor/calendar"


@router.post(f"{PANEL_URL}/{{mark_id}}/end", response_class=HTMLResponse)
async def update_unavailability_end(
    mark_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Меняет срок отметки; чужую отметку не раскрывает (404)."""
    mark = get_owned_unavailability(db, mark_id, tutor_id)
    form = await request.form()
    new_end, errors = parse_end_form(form)

    if not errors:
        errors = change_end(db, mark, new_end)

    if errors:
        # Панель возвращается с ошибкой, срок в БД не изменён (D9).
        return templates.TemplateResponse(
            request,
            "unavailability/_panel.html",
            panel_context(db, tutor_id, errors=errors),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=CALENDAR_URL, status_code=303)

    response = templates.TemplateResponse(
        request,
        "unavailability/_panel.html",
        panel_context(db, tutor_id, saved=True),
    )
    response.headers["HX-Trigger"] = "unavailability-saved"
    return response
