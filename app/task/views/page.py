"""Страница «Задачи»: канбан-доска или список по срокам.

`GET /tutor/tasks` — полный рендер страницы: заголовок, переключатель
вида, фильтр по ученику и контент. Вид и фильтр — query-параметры
(`view`, `student`), а не клиентское состояние: страница работает без JS,
состояние видно в адресе, а оба вида считает сервер одним сервисом.

Контент живёт в партиале `/tutor/tasks/list`: после сохранения или
удаления задачи событие `task-saved` перезапрашивает его, и доска
обновляется без перезагрузки страницы.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.services.tutor_time import today_local
from app.database import get_db
from app.task.services.access import LoginRequired, require_tutor_id
from app.task.services.board import normalize_view, tasks_context
from app.task.services.student_options import student_options
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

TASKS_URL = "/tutor/tasks"


@router.get(TASKS_URL, response_class=HTMLResponse)
def tasks_page(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Задачи вошедшего репетитора; без сессии — редирект на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        raise LoginRequired()

    view = normalize_view(request.query_params.get("view", ""))
    student_id = request.query_params.get("student", "")
    context = tasks_context(
        db,
        tutor_id,
        today=today_local(tutor),
        view=view,
        student_id=student_id,
    )
    context.update(
        {
            "active_page": "tasks",
            "user_name": tutor.name,
            "user_role": "Владелец",
            "tutor": tutor,
            "student_options": student_options(db, tutor_id),
        }
    )
    return templates.TemplateResponse(request, "task/index.html", context)
