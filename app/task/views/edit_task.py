"""Диалог правки задачи (GET).

Клик по карточке открывает форму с заполненными полями: название,
приоритет, срок, этап, описание и привязанные ученики. Чужая или
несуществующая задача — 404 (изоляция по репетитору).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.task.services.access import get_owned_task, require_tutor_id
from app.task.services.task_dialog import task_dialog_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

TASKS_URL = "/tutor/tasks"


@router.get(f"{TASKS_URL}/{{task_id}}/edit", response_class=HTMLResponse)
def edit_task_dialog(
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Форма правимой задачи; чужая задача отвечает как несуществующая."""
    task = get_owned_task(db, task_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "task/_dialog.html",
        task_dialog_context(db, tutor, task=task),
    )
