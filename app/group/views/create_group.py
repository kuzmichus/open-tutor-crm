"""Создание группы: обработка формы и обновление списка.

Успех закрывает модалку и поднимает событие `group-saved`: сетка
`#groups-grid` перезапрашивает партиал `/tutor/groups/list`, поэтому
страница не перезагружается (спека group-management).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.form_context import (
    NEW_GROUP_SUBTITLE,
    NEW_GROUP_TITLE,
    form_from_data,
    group_form_context,
    submitted_member_rows,
)
from app.group.services.group_form import parse_group_form
from app.group.services.group_writer import create_group
from app.templating import templates

router = APIRouter()


def _is_htmx(request: Request) -> bool:
    """True, если запрос пришёл от htmx (не полная навигация браузера)."""
    return request.headers.get("HX-Request") == "true"


def _form_response(
    request: Request,
    db: Session,
    tutor_id: str,
    data: dict,
    errors: list[str],
) -> HTMLResponse:
    """Повторная отрисовка модалки с ошибками и введённым составом."""
    context = group_form_context(
        db,
        tutor_id,
        form=form_from_data(data),
        member_rows=submitted_member_rows(db, tutor_id, data),
        action="/tutor/groups",
        title=NEW_GROUP_TITLE,
        subtitle=NEW_GROUP_SUBTITLE,
        errors=errors,
        # Уже добавленные в форме ученики не предлагаются повторно:
        # повторный выбор создал бы дубль (спека group-membership).
        exclude_ids=data.get("member_ids", []),
    )
    return templates.TemplateResponse(request, "group/_new_group.html", context)


@router.post("/tutor/groups", response_class=HTMLResponse)
async def create_group_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт группу; `tutor_id` берётся только из сессии."""
    form = await request.form()
    data, errors = parse_group_form(form)

    if errors:
        return _form_response(request, db, tutor_id, data, errors)

    group, save_errors = create_group(db, tutor_id, data)
    if save_errors:
        return _form_response(request, db, tutor_id, data, save_errors)

    if not _is_htmx(request):
        return RedirectResponse(url="/tutor/groups", status_code=303)

    # Пустой ответ очищает `#modal`, событие перезапрашивает сетку.
    response = HTMLResponse("")
    response.headers["HX-Trigger"] = "group-saved"
    return response
