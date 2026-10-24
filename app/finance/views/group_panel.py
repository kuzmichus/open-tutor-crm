"""Вкладка «Оплаты» группы — фрагмент модалки управления (design D1).

Панель приходит лениво: слот вкладки «Оплаты» в `_manage.html` запрашивает
её с `hx-trigger="load"`, чипы периода перезапрашивают тот же маршрут.
Отдельный HTML-эндпоинт, а не данные внутри формы группы: модалка —
единая `<form>`, и всё, что попадает в неё, уходило бы в POST, а пересчёт
сводки при каждой отрисовке с ошибкой валидации был бы лишним (тот же
паттерн, что у панели платежей ученика).

Маршрут живёт в пространстве `/tutor/groups`, но по домену это счёт:
итоги и строки участников считает сервис `finance.services.group_panel`,
а владелец группы проверяется ри-экспортом `get_owned_group` — чужая
группа и несуществующая неразличимы: 404.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import get_owned_group, require_tutor_id
from app.finance.services.group_panel import group_panel_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get(
    "/tutor/groups/{group_id}/payments",
    response_class=HTMLResponse,
)
def group_payments_panel(
    request: Request,
    group_id: str,
    period: str = "",
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Сводка оплат группы; чужая группа — 404, неизвестный период — «За всё время»."""
    group = get_owned_group(db, group_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "finance/_group_panel.html",
        {
            "payments": group_panel_context(db, group, tutor, period=period),
        },
    )
