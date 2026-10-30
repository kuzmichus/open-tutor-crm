"""Сохранение задачи (POST `/{task_id}`).

Правка меняет поля задачи, её учеников и этап; смена этапа синхронизирует
момент завершения (`task_writer.set_stage`). Чужая или несуществующая
задача — 404. Ошибки возвращают диалог, успех — пустое тело с
`task-saved`, и доска перезапрашивает партиал.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed, is_htmx
from app.database import get_db
from app.task.services.access import get_owned_task, require_tutor_id
from app.task.services.task_dialog import task_dialog_context
from app.task.services.task_form import parse_task_form
from app.task.services.task_writer import update_task
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

TASKS_URL = "/tutor/tasks"


@router.post(f"{TASKS_URL}/{{task_id}}", response_class=HTMLResponse)
async def update_task_view(
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет задачу; чужая задача отвечает как несуществующая."""
    task = get_owned_task(db, task_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)

    form = await request.form()
    data, errors = parse_task_form(form)

    if not errors:
        _, errors = update_task(db, task, tutor_id, data)

    if errors:
        return templates.TemplateResponse(
            request,
            "task/_dialog.html",
            task_dialog_context(db, tutor, task=task, data=data, errors=errors),
        )

    if not is_htmx(request):
        return RedirectResponse(url=TASKS_URL, status_code=303)
    return dialog_closed("task-saved")
