"""Сохранение настроек группы: поля, состав, даты, цены, исключения.

Форма модалки управления отправляет и «Общее», и «Настройки» (все панели
в DOM, решение D3), поэтому один POST применяет всё сразу. Ошибки
валидации возвращаются в модалку с введёнными значениями и открытой
вкладкой «Настройки».
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.access import get_owned_group
from app.group.services.form_context import (
    form_from_data,
    manage_context,
    submitted_member_rows,
)
from app.group.services.group_form import parse_group_form
from app.group.services.group_writer import update_group
from app.templating import templates

router = APIRouter()


def _is_htmx(request: Request) -> bool:
    """True, если запрос пришёл от htmx (не полная навигация браузера)."""
    return request.headers.get("HX-Request") == "true"


def _form_response(
    request: Request,
    db: Session,
    tutor_id: str,
    group,
    data: dict,
    errors: list[str],
) -> HTMLResponse:
    """Повторная отрисовка модалки с ошибками и введённым составом."""
    context = manage_context(
        db,
        tutor_id,
        group,
        form=form_from_data(data),
        member_rows=submitted_member_rows(db, tutor_id, data),
        errors=errors,
        tab="settings",
    )
    return templates.TemplateResponse(request, "group/_manage.html", context)


@router.post("/tutor/groups/{group_id}", response_class=HTMLResponse)
async def update_group_view(
    request: Request,
    group_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Применяет изменения группы; чужая группа — 404."""
    group = get_owned_group(db, group_id, tutor_id)
    form = await request.form()
    data, errors = parse_group_form(form)

    if errors:
        return _form_response(request, db, tutor_id, group, data, errors)

    save_errors = update_group(db, group, tutor_id, data)
    if save_errors:
        return _form_response(request, db, tutor_id, group, data, save_errors)

    if not _is_htmx(request):
        return RedirectResponse(url="/tutor/groups", status_code=303)

    # Пустой ответ очищает `#modal`, событие перезапрашивает сетку.
    response = HTMLResponse("")
    response.headers["HX-Trigger"] = "group-saved"
    return response
