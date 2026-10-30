"""Выгрузка прогноза на месяц в CSV (GET `/tutor/finance/forecast.csv`).

Файл собирается тем же контекстом, что и вкладка: цифры в таблице и на
экране не могут разойтись, потому что источник у них один. Скачивание —
обычная ссылка, а не htmx: браузер сам отдаёт файл, страница не меняется.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.forecast import (
    forecast_context,
    forecast_csv,
    parse_forecast_month,
)
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/finance/forecast.csv")
def finance_forecast_csv(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> Response:
    """CSV прогноза за месяц; без сессии — редирект на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    month = parse_forecast_month(request.query_params, tutor)
    content = forecast_csv(forecast_context(db, tutor, month=month))
    filename = f"forecast-{month['year']}-{month['month']:02d}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
