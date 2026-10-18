"""Форма создания ученика (модальное окно)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import require_tutor_id
from app.student.services.form_context import form_context, new_student_form_context
from app.templating import templates

router = APIRouter()


@router.get("/tutor/students/new", response_class=HTMLResponse)
def new_student_form(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма создания для вставки в контейнер `#modal`."""
    context = form_context(
        db, new_student_form_context()["form"], tutor_id=tutor_id
    )
    return templates.TemplateResponse(request, "student/_form.html", context)
