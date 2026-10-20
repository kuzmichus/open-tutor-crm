"""Создание группы из мини-формы селекта урока (решение D7).

Мини-форма — два поля (Название*, Цена за урок) без состава: разбор
и валидация переиспользуют создание группы (`parse_group_form` +
`create_group` из `app/group/services/`), поэтому название проверяется
теми же правилами, а пустое обязательное поле блокирует создание.

Ответ — транспортный фрагмент `lesson/_target_update.html` с выбранной
записью (`data-selected`): Alpine закрывает мини-форму и вписывает
группу в поле селекта. Ошибка валидации возвращается тем же фрагментом
с `data-error` — мини-форма остаётся открытой с сообщением.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.group_form import parse_group_form
from app.group.services.group_writer import create_group
from app.templating import templates

router = APIRouter()


def _update_response(
    request: Request,
    *,
    selected: dict | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """Транспортный фрагмент ответа мини-формы (как `_member_update.html`)."""
    return templates.TemplateResponse(
        request,
        "lesson/_target_update.html",
        {
            "kind": "group",
            "selected": selected,
            "error": error,
        },
    )


@router.post("/tutor/lessons/groups", response_class=HTMLResponse)
async def create_lesson_group(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Создаёт группу и возвращает её как выбранную цель урока."""
    form = await request.form()
    data, errors = parse_group_form(form)

    if errors:
        return _update_response(request, error=errors[0])

    group, errors = create_group(db, tutor_id, data)
    if errors:
        return _update_response(request, error=errors[0])

    return _update_response(
        request,
        selected={"id": group.id, "name": group.name},
    )
