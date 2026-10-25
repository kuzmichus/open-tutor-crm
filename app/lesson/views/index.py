"""Список уроков: страница с таблицей, фильтрами и поиском.

`tutor_id` приходит только из сессии (`require_tutor_id`), поэтому в выборку
не попадают уроки других репетиторов (спека lesson-management).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.lesson.services.lessons import list_lessons, normalize_period, normalize_status
from app.lesson.services.lookup import search_students
from app.lesson.services.page_context import page_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/lessons", response_class=HTMLResponse)
def lessons_index(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Страница со списком уроков вошедшего репетитора."""
    q = request.query_params.get("q", "")
    period = normalize_period(request.query_params.get("period", ""))
    status = normalize_status(request.query_params.get("status", ""))
    student_id = request.query_params.get("student", "")
    tutor = db.get(Tutor, tutor_id)
    rows = list_lessons(
        db,
        tutor_id,
        q=q,
        period=period,
        status=status,
        student_id=student_id,
        tutor=tutor,
    )

    return templates.TemplateResponse(
        request,
        "lesson/index.html",
        page_context(
            db,
            tutor_id,
            rows=rows,
            total=len(rows),
            q=q,
            period=period,
            status=status,
            student_id=student_id,
            student_options=search_students(db, tutor_id),
        ),
    )
