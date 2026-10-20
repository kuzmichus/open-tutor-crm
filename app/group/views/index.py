"""Список групп: страница с сеткой карточек.

`tutor_id` приходит только из сессии (`require_tutor_id`), поэтому в выборку
не попадают группы других репетиторов (спека group-management).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.groups import group_options
from app.group.services.page_context import page_context
from app.templating import templates

router = APIRouter()


@router.get("/tutor/groups", response_class=HTMLResponse)
def groups_index(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Страница со списком групп вошедшего репетитора."""
    options = group_options(db, tutor_id)

    return templates.TemplateResponse(
        request,
        "group/index.html",
        page_context(
            db,
            tutor_id,
            options=options,
            total=len(options),
        ),
    )
