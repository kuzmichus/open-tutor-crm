"""Массовая отметка уроков проведёнными (change lessons-table-scale).

Один POST на весь выбор: чекбоксы строк отправляют повторяющееся поле
`lesson_id`, сервис переводит запланированные уроки в «Проведён» и
пересчитывает списания. Страница обновляет таблицу событием
`lesson-saved` — тем же, что и сохранение одного урока, поэтому второго
слушателя не нужно.

Маршрут статический (`/complete-selected`) и регистрируется **до**
`POST /tutor/lessons/{lesson_id}`: иначе параметрический путь принял бы
`complete-selected` за id урока.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.responses import saved_response
from app.database import get_db
from app.lesson.services.access import require_tutor_id
from app.lesson.services.lesson_bulk import complete_lessons

router = APIRouter()

LESSONS_URL = "/tutor/lessons"


@router.post(f"{LESSONS_URL}/complete-selected", response_class=HTMLResponse)
async def complete_selected_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Отмечает выбранные уроки проведёнными; чужие id игнорируются.

    Ничего не выбрано — запрос не ошибка: таблица просто перезапрашивается.
    Сообщать «выберите хотя бы один урок» незачем, кнопка и так нажимается
    только рядом с чекбоксами.
    """
    form = await request.form()
    lesson_ids = [value for value in form.getlist("lesson_id") if value]

    complete_lessons(db, tutor_id, lesson_ids)
    db.commit()

    return saved_response(request, "lesson-saved", LESSONS_URL)
