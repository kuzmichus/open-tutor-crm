"""Партиал списка броней для htmx.

`GET /tutor/bookings/list` — фрагмент без сайдбара: его перезапрашивает
контейнер `#bookings-content` по событию `slot-saved` (успешные действия
с бронью шлют его из диалога окна и прямых кнопок страницы).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.booking.services.access import require_tutor_id
from app.booking.services.booking_list import tutor_bookings
from app.common.services.tutor_time import now_utc
from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

BOOKINGS_URL = "/tutor/bookings"


@router.get(f"{BOOKINGS_URL}/list", response_class=HTMLResponse)
def bookings_list_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Список броней (ожидание + история) фрагментом для контейнера."""
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "booking/_list.html",
        {
            "tutor": tutor,
            "bookings": tutor_bookings(db, tutor_id, tutor, now=now_utc()),
        },
    )
