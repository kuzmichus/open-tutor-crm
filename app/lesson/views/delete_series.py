"""Удаление всей серии урока (красная кнопка «Серию» с подтверждением).

Удаляются все уроки серии и сама серия; у одиночного урока кнопки нет
в форме, а POST без `series_id` отвечает 404 — как несуществующая серия.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import is_htmx
from app.database import get_db
from app.lesson.services.access import get_owned_lesson, require_tutor_id
from app.lesson.services.lesson_remover import delete_series

router = APIRouter()

LESSONS_URL = "/tutor/lessons"


@router.post(
    f"{LESSONS_URL}/{{lesson_id}}/delete-series", response_class=HTMLResponse
)
def delete_series_view(
    lesson_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Удаляет серию целиком; у одиночного урока — 404."""
    lesson = get_owned_lesson(db, lesson_id, tutor_id)
    if lesson.series_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    delete_series(db, lesson.series_id)

    if not is_htmx(request):
        return RedirectResponse(url=LESSONS_URL, status_code=303)
    return HTMLResponse(content="", headers={"HX-Trigger": "lesson-saved"})
