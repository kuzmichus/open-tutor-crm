"""Вкладка «Занятия» группы — фрагмент модалки управления (паттерн оплат).

Панель приходит лениво: слот вкладки «Занятия» в `group/_manage.html`
запрашивает её с `hx-trigger="load"`, чипы статуса перезапрашивают тот
же маршрут. Отдельный HTML-эндпоинт, а не данные внутри формы группы:
модалка — единая `<form>`, и всё, что попадает в неё, уходило бы в POST
(тот же паттерн, что у панели оплат группы).

Маршрут живёт в пространстве `/tutor/groups`, но по домену это уроки:
выборку делает `lesson.services.group_lessons`, а владелец группы
проверяется ри-экспортом `get_owned_group` — чужая группа и
несуществующая неразличимы: 404.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.lesson.services.access import get_owned_group, require_tutor_id
from app.lesson.services.group_lessons import list_group_lessons
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get(
    "/tutor/groups/{group_id}/lessons",
    response_class=HTMLResponse,
)
def group_lessons_panel(
    request: Request,
    group_id: str,
    status: str = "",
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Список занятий группы; чужая группа — 404, неизвестный статус — «Все»."""
    group = get_owned_group(db, group_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "lesson/_group_panel.html",
        {
            "group": group,
            "tutor": tutor,
            "status": status,
            "rows": list_group_lessons(db, group, status=status),
        },
    )
