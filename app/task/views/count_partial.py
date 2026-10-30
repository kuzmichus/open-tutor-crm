"""Счётчик просроченных задач — партиал для пункта «Задачи» сайдбара.

`GET /tutor/tasks/count` — число задач этого репетитора с истекшим сроком,
ещё не переведённых в «Готово». Контейнер в `sidebar.html` сам запрашивает
эндпоинт (`hx-trigger="load"`), перечитывает его каждые 30 секунд (просрочка
наступает сама, без событий у педагога) и по `task-saved` — сохранение,
удаление и смена этапа обновляют счётчик мгновенно.

Ноль просроченных — пустое тело: контейнер остаётся без кружка, ноль
не сигнал к действию (тот же приём, что у счётчика «Броней»).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.services.tutor_time import today_local
from app.database import get_db
from app.task.services.access import require_tutor_id
from app.task.services.board import overdue_count
from app.tutor.models.tutor import Tutor

router = APIRouter()

TASKS_URL = "/tutor/tasks"


@router.get(f"{TASKS_URL}/count", response_class=HTMLResponse)
def tasks_count_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Число просроченных задач; без сессии — редирект на вход."""
    tutor = db.get(Tutor, tutor_id)
    count = overdue_count(db, tutor_id, today=today_local(tutor))
    return HTMLResponse(content=str(count) if count else "")
