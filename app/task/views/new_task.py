"""Диалог новой задачи (GET).

Открывается кнопкой «Новая задача» в контейнер `#modal`: форма приходит
свопом уже открытой (паттерн `finance/views/expense_new.py`). Сохранение —
`create_task.py`, успех шлёт `task-saved`, и контейнер `#tasks-content`
перезапрашивает партиал.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.task.services.access import LoginRequired, require_tutor_id
from app.task.services.task_dialog import task_dialog_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

TASKS_URL = "/tutor/tasks"


@router.get(f"{TASKS_URL}/new", response_class=HTMLResponse)
def new_task_dialog(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма задачи; без сессии — редирект на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        raise LoginRequired()

    return templates.TemplateResponse(
        request,
        "task/_dialog.html",
        task_dialog_context(db, tutor),
    )
