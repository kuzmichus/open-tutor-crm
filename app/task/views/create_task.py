"""Создание задачи (POST).

Ошибки валидации возвращают диалог с сообщениями и введёнными значениями;
успех — пустое тело с событием `task-saved` (контейнер доски
перезапрашивает партиал). Без `HX-Request` POST отвечает 303 на страницу
задач — форма работает и без JS (паттерн `finance/views/expense_create.py`).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed, is_htmx
from app.database import get_db
from app.task.services.access import LoginRequired, require_tutor_id
from app.task.services.task_dialog import task_dialog_context
from app.task.services.task_form import parse_task_form
from app.task.services.task_writer import create_task
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

TASKS_URL = "/tutor/tasks"


@router.post(TASKS_URL, response_class=HTMLResponse)
async def create_task_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт задачу; `tutor_id` — только из сессии."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = await request.form()
    data, errors = parse_task_form(form)

    if not errors:
        _, errors = create_task(db, tutor_id, data)

    if errors:
        return templates.TemplateResponse(
            request,
            "task/_dialog.html",
            task_dialog_context(db, tutor, data=data, errors=errors),
        )

    if not is_htmx(request):
        return RedirectResponse(url=TASKS_URL, status_code=303)
    return dialog_closed("task-saved")
