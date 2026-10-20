"""Модалка создания группы."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.form_context import empty_group_form, group_form_context
from app.templating import templates

router = APIRouter()


@router.get("/tutor/groups/new", response_class=HTMLResponse)
def new_group_form(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма создания для вставки в контейнер `#modal`."""
    context = group_form_context(
        db,
        tutor_id,
        form=empty_group_form(),
        member_rows=[],
        action="/tutor/groups",
        title="Новая группа",
        subtitle=(
            "Создайте группу для нескольких учеников. "
            "Вы сможете назначать уроки сразу всей группе."
        ),
    )
    return templates.TemplateResponse(request, "group/_new_group.html", context)
