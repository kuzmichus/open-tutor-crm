"""Смена этапа задачи (POST `/{task_id}/stage`).

Перетаскивание карточки между колонками доски: `stage` приходит полем
формы и обязан быть значением из закрытого списка модели — мусор
отклоняется 400, а не молча превращается в «Новые». Этап синхронизирует
момент завершения (`task_writer.set_stage`).

Ответ — пустое тело с `task-saved`: доска перезапрашивает партиал, и
порядок карточек внутри колонки пересчитывается на сервере (в браузере
сортировок нет).
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed, is_htmx
from app.database import get_db
from app.task.services.access import get_owned_task, require_tutor_id
from app.task.services.task_writer import move_task, parse_stage

router = APIRouter()

TASKS_URL = "/tutor/tasks"


@router.post(f"{TASKS_URL}/{{task_id}}/stage", response_class=HTMLResponse)
def move_task_view(
    task_id: str,
    request: Request,
    stage: str = Form(""),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Переводит задачу на этап; чужая задача — 404, мусор в этапе — 400."""
    task = get_owned_task(db, task_id, tutor_id)
    target = parse_stage(stage)
    if target is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    move_task(db, task, target)

    if not is_htmx(request):
        return RedirectResponse(url=TASKS_URL, status_code=303)
    return dialog_closed("task-saved")
