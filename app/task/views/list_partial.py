"""Партиал задач для htmx.

`GET /tutor/tasks/list` — фрагмент без сайдбара: его перезапрашивает
контейнер `#tasks-content` по событию `task-saved` (его шлют сохранение,
удаление и смена этапа). Вид и фильтр приходят теми же query-параметрами,
что у страницы, — контейнер передаёт их через `hx-include`.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.services.tutor_time import today_local
from app.database import get_db
from app.task.services.access import require_tutor_id
from app.task.services.board import normalize_view, tasks_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

TASKS_URL = "/tutor/tasks"


@router.get(f"{TASKS_URL}/list", response_class=HTMLResponse)
def tasks_list_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Доска или список задач фрагментом для контейнера."""
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "task/_content.html",
        tasks_context(
            db,
            tutor_id,
            today=today_local(tutor),
            view=normalize_view(request.query_params.get("view", "")),
            student_id=request.query_params.get("student", ""),
        ),
    )
