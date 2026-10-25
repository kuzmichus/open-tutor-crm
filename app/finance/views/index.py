"""Страница финансов: сводка за период и кнопки «Доход»/«Расход».

Страница только читает данные: запись идёт диалогами «Доход» и «Расход».
Период и вкладка — query-параметры обычной GET-формы и ссылок: страница
работает без JS, её состояние видно в адресе (паттерн `/tutor/stats`).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.operations_feed import parse_finance_tab
from app.finance.services.operations_section import operations_context
from app.finance.services.periods import (
    PERIOD_LABELS,
    PERIOD_OPTIONS,
    parse_finance_period,
)
from app.finance.services.summary import summary_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/finance", response_class=HTMLResponse)
def finance_index(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Финансы вошедшего репетитора; без сессии — редирект на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        raise LoginRequired()

    period = parse_finance_period(request.query_params, tutor)
    tab = parse_finance_tab(request.query_params)
    context = {
        "active_page": "finance",
        "user_name": tutor.name,
        "user_role": "Владелец",
        "tutor": tutor,
        "period": period,
        "period_options": PERIOD_OPTIONS,
        "period_labels": PERIOD_LABELS,
        "summary": summary_context(
            db, tutor_id, start=period["start"], end=period["end"]
        ),
    }
    context.update(operations_context(db, tutor, period=period, tab=tab))
    return templates.TemplateResponse(request, "finance/index.html", context)
