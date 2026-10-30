"""Партиал секции операций (GET `/tutor/finance/operations`).

Секция перезапрашивает себя по `payment-saved` и `expense-saved`: строки
списка, вкладка и карточка балансов приезжают заново с сервера — в браузере
нет ни одной денежной формулы (паттерн `finance/_summary.html`).

Состояние разбирает тот же `parse_state`, что у страницы и у ручки вкладки:
мусор в query заменяется умолчаниями одинаково, и адрес перезапроса
(`refresh_url`) не расходится с нарисованным. Историю браузера этот ответ
не двигает: это обновление уже открытой страницы, а не переход.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.operations_section import (
    operations_context,
    parse_state,
)
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/finance/operations", response_class=HTMLResponse)
def finance_operations(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Табы, список операций и балансы за период; без сессии — на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    state = parse_state(request.query_params, tutor)
    return templates.TemplateResponse(
        request,
        "finance/_operations.html",
        operations_context(db, tutor, **state),
    )
