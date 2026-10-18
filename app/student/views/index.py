"""Список учеников: страница с сеткой карточек, поиском и фильтром."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import require_tutor_id
from app.student.services.page_context import page_context
from app.student.services.students import build_cards, list_students
from app.templating import templates

router = APIRouter()


@router.get("/tutor/students", response_class=HTMLResponse)
def students_index(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Страница со списком учеников вошедшего репетитора."""
    q = request.query_params.get("q", "")
    status = request.query_params.get("status", "")
    students = list_students(db, tutor_id, q=q, status=status)
    cards = build_cards(db, students)

    return templates.TemplateResponse(
        request,
        "student/index.html",
        page_context(
            db,
            request,
            tutor_id,
            cards=cards,
            total=len(cards),
        ),
    )
