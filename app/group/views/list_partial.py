"""Партиал сетки групп для htmx (подмена после создания и удаления).

Отдаёт только карточки или пустое состояние — без страницы и сайдбара,
чтобы ответ можно было вставить в `#groups-grid`.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.groups import group_options
from app.templating import templates

router = APIRouter()


@router.get("/tutor/groups/list", response_class=HTMLResponse)
def groups_list_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Сетка карточек групп вошедшего репетитора."""
    options = group_options(db, tutor_id)

    return templates.TemplateResponse(
        request,
        "group/_grid.html",
        {"options": options, "total": len(options)},
    )
