"""Фиксация прогноза на месяц (POST `/tutor/finance/forecast/pin`).

Снимок сохраняет текущий диапазон «Итого за месяц»: позже карточка
«Прогноз vs факт» сравнивает его с реальными списаниями. Значения
пересчитываются на сервере (`services/forecast.py`), форма их не
передаёт — иначе снимком можно было бы записать число, которого не было
на экране.

Ответ — 303 на вкладку прогноза с сохранённым месяцем: страница
перезагружается и показывает карточку сравнения. HTMX здесь не нужен:
фиксация — редкое осознанное действие, а не поток правок.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.forecast import parse_forecast_month, pin_forecast
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.post("/tutor/finance/forecast/pin")
def finance_forecast_pin(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> RedirectResponse:
    """Сохраняет снимок прогноза и возвращает на вкладку прогноза."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    month = parse_forecast_month(request.query_params, tutor)
    pin_forecast(db, tutor, month=month)
    return RedirectResponse(
        url=f"/tutor/finance?tab=forecast&month={month['key']}", status_code=303
    )
