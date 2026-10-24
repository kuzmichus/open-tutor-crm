"""Форма редактирования ученика (модальное окно)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import get_owned_student, require_tutor_id
from app.student.services.form_context import (
    edit_student_form_context,
    form_context,
    normalize_tab,
)
from app.templating import templates

router = APIRouter()

def _is_from_card(request: Request) -> bool:
    """True, если форму открыли со страницы карточки ученика.

    На карточке нет сетки, поэтому после сохранения обновляется страница,
    а не карточка в сетке.
    """
    return request.query_params.get("from_card") == "1"

@router.get("/tutor/students/{student_id}/edit", response_class=HTMLResponse)
def edit_student_form(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Форма редактирования; чужой ученик — 404.

    `?tab=payments` открывает карточку сразу на вкладке «Платежи» — так
    работает действие «Платежи» в сводке счёта на странице ученика
    (design D12). Неизвестная вкладка сводится к «Общему».
    """
    student = get_owned_student(db, student_id, tutor_id)
    context = form_context(
        db,
        edit_student_form_context(db, student)["form"],
        tutor_id=tutor_id,
        student=student,
        from_card=_is_from_card(request),
        tab=normalize_tab(request.query_params.get("tab")),
    )
    return templates.TemplateResponse(request, "student/_form.html", context)
