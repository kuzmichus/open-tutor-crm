"""Модалка управления группой: пять вкладок, «Общее» активна по умолчанию."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.access import get_owned_group
from app.group.services.form_context import manage_context
from app.templating import templates

router = APIRouter()


@router.get("/tutor/groups/{group_id}/edit", response_class=HTMLResponse)
def edit_group_modal(
    request: Request,
    group_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Модалка управления; чужая группа отвечает как отсутствующая (404)."""
    group = get_owned_group(db, group_id, tutor_id)
    context = manage_context(db, tutor_id, group)
    return templates.TemplateResponse(request, "group/_manage.html", context)
