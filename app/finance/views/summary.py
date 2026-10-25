"""Партиал сводки финансов (`/tutor/finance/summary`).

Отдельный роут ради перезапроса после сохранения платежа (design D6):
диалог отвечает `HX-Trigger: payment-saved`, контейнер `#finance-summary`
запрашивает себя заново — числа обновляются с сервера, а не пересчитываются
в браузере. Тот же контекст считает и полная страница, поэтому числа
страницы и партиала не могут разойтись.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.periods import parse_finance_period
from app.finance.services.summary import summary_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/finance/summary", response_class=HTMLResponse)
def finance_summary(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Сводка за период вошедшего репетитора; без сессии — на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    period = parse_finance_period(request.query_params, tutor)
    return templates.TemplateResponse(
        request,
        "finance/_summary.html",
        {
            "period": period,
            "summary": summary_context(
                db, tutor_id, start=period["start"], end=period["end"]
            ),
        },
    )
