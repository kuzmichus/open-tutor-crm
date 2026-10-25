"""Партиал таблицы уроков для htmx (фильтры и поиск без перезагрузки)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.lesson.services.lessons import (
    list_lessons,
    normalize_period,
    normalize_status,
)
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/lessons/list", response_class=HTMLResponse)
def lessons_list_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Таблица с учётом поиска `q`, фильтров `period`/`status` и ученика."""
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
        "lesson/_table.html",
        {
            "rows": rows,
            "q": q,
            "period": period,
            "status": status,
            "student_id": student_id,
            "tutor": tutor,
        },
    )
