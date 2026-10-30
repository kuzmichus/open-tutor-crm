"""Список уроков: страница с таблицей, фильтрами, сортировкой и пагинацией.

`tutor_id` приходит только из сессии (`require_tutor_id`), поэтому в выборку
не попадают уроки других репетиторов (спека lesson-management).

Сортировка и пагинация — query-параметры (`sort`, `direction`, `page`), а не
клиентское состояние: страница работает без JS, а ссылки заголовков и
пагинации остаются обычными `href` (change lessons-table-scale).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.lesson.services.lookup import search_students
from app.lesson.services.page_context import page_context
from app.lesson.services.table_context import table_context
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
    tutor = db.get(Tutor, tutor_id)
    context = table_context(
        db,
        tutor_id,
        tutor,
        q=request.query_params.get("q", ""),
        period=request.query_params.get("period", ""),
        status=request.query_params.get("status", ""),
        student_id=request.query_params.get("student", ""),
        sort=request.query_params.get("sort", ""),
        direction=request.query_params.get("direction", ""),
        page=request.query_params.get("page", ""),
        student_options=search_students(db, tutor_id),
    )

    return templates.TemplateResponse(
        request,
        "lesson/index.html",
        page_context(db, tutor_id, **context),
    )
