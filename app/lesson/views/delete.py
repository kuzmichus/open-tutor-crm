"""Удаление одного урока (кнопка «Удалить» с двухшаговым подтверждением).

После удаления окно закрывается пустым ответом, список обновляется
событием `lesson-saved` (спека: «После удаления окно закрывается,
список обновляется»).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.lesson.services.access import get_owned_lesson, require_tutor_id
from app.lesson.services.lesson_remover import delete_lesson

router = APIRouter()

LESSONS_URL = "/tutor/lessons"


@router.post(f"{LESSONS_URL}/{{lesson_id}}/delete", response_class=HTMLResponse)
def delete_lesson_view(
    lesson_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Удаляет урок; чужой урок отвечает как несуществующий (404)."""
    lesson = get_owned_lesson(db, lesson_id, tutor_id)
    delete_lesson(db, lesson)

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=LESSONS_URL, status_code=303)
    return HTMLResponse(content="", headers={"HX-Trigger": "lesson-saved"})
