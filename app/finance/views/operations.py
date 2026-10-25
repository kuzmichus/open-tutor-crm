"""Партиал секции операций (GET `/tutor/finance/operations`).

Секция перезапрашивает себя по `payment-saved` и `expense-saved`: строки
списка, вкладка и карточка балансов приезжают заново с сервера — в браузере
нет ни одной денежной формулы (паттерн `finance/_summary.html`).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.operations_feed import parse_finance_tab
from app.finance.services.operations_section import operations_context
from app.finance.services.periods import parse_finance_period
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

    period = parse_finance_period(request.query_params, tutor)
    tab = parse_finance_tab(request.query_params)
    return templates.TemplateResponse(
        request,
        "finance/_operations.html",
        operations_context(db, tutor, period=period, tab=tab),
    )
