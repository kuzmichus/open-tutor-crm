"""Удаление одного урока (кнопка «Удалить» с двухшаговым подтверждением).

После удаления окно закрывается пустым ответом, список обновляется
событием `lesson-saved` (спека: «После удаления окно закрывается,
список обновляется»).

Событие в Google удаляется **до** удаления урока: строка
`calendar_events` уходит каскадом вместе с уроком, и после него id
события уже не узнать (design D7).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.responses import saved_response
from app.database import get_db
from app.gcalendar.services.sync import delete_lesson_event
from app.lesson.services.access import get_owned_lesson, require_tutor_id
from app.lesson.services.lesson_remover import delete_lesson
from app.tutor.models.tutor import Tutor

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
    tutor = db.get(Tutor, tutor_id)
    # До `delete_lesson`: каскад сносит строку соответствия, и событие в
    # Google осталось бы навсегда (design D7).
    delete_lesson_event(db, tutor, lesson)
    delete_lesson(db, lesson)

    return saved_response(request, "lesson-saved", LESSONS_URL)
