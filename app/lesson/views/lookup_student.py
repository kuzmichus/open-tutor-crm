"""Поиск учеников для селекта цели урока.

Фрагмент списка выбора: свои ученики, только активные/новые — архивные
и чужие не отдаются (спека lesson-management). Пустой `q` — весь список:
список открывается по клику без ожидания ввода. `tutor_id` — только
из сессии, без неё — редирект на вход.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.lesson.services.lookup import search_students
from app.templating import templates

router = APIRouter()


@router.get("/tutor/lessons/lookup/students", response_class=HTMLResponse)
def lookup_lesson_students(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Фрагмент списка выбора ученика: поиск по имени, параметр `q`."""
    q = request.query_params.get("q", "")
    return templates.TemplateResponse(
        request,
        "lesson/_lookup_options.html",
        {"options": search_students(db, tutor_id, q=q)},
    )
