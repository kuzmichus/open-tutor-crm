"""Партиал сетки учеников для htmx (поиск и фильтр без перезагрузки)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import require_tutor_id
from app.student.services.students import build_cards, list_students
from app.templating import templates

router = APIRouter()


@router.get("/tutor/students/list", response_class=HTMLResponse)
def students_list_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Сетка карточек с учётом поиска `q` и фильтра `status`."""
    q = request.query_params.get("q", "")
    status = request.query_params.get("status", "")
    students = list_students(db, tutor_id, q=q, status=status)
    cards = build_cards(db, students)

    return templates.TemplateResponse(
        request,
        "student/_grid.html",
        {"cards": cards, "q": q, "status": status, "total": len(cards)},
    )
