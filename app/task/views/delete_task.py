"""Удаление задачи (POST `/{task_id}/delete`).

Действие из диалога правки. Чужая или несуществующая задача — 404;
успех — пустое тело с `task-saved`, доска перезапрашивает партиал.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed, is_htmx
from app.database import get_db
from app.task.services.access import get_owned_task, require_tutor_id
from app.task.services.task_writer import delete_task

router = APIRouter()

TASKS_URL = "/tutor/tasks"


@router.post(f"{TASKS_URL}/{{task_id}}/delete", response_class=HTMLResponse)
def delete_task_view(
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Удаляет задачу; чужая задача отвечает как несуществующая."""
    task = get_owned_task(db, task_id, tutor_id)
    delete_task(db, task)

    if not is_htmx(request):
        return RedirectResponse(url=TASKS_URL, status_code=303)
    return dialog_closed("task-saved")
