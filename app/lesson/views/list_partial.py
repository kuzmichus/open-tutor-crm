"""Партиал таблицы уроков для htmx (фильтры, сортировка, пагинация).

Контекст собирает тот же `table_context`, что и страница: полная загрузка и
фильтрация не должны расходиться в порядке строк и разметке пагинации
(change lessons-table-scale).

Ссылки пагинации ведут на страницу целиком (`/tutor/lessons?...`), но
внутри htmx перехватываются: контейнер таблицы слушает `click` по своим
ссылкам и перезапрашивает партиал — без перезагрузки страницы.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.lesson.services.lookup import search_students
from app.lesson.services.table_context import table_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/lessons/list", response_class=HTMLResponse)
def lessons_list_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Таблица с учётом поиска, фильтров, сортировки и страницы."""
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

    return templates.TemplateResponse(request, "lesson/_table.html", context)
