"""Счётчик необработанных заявок — партиал для пункта «Брони» сайдбара.

`GET /tutor/bookings/count` — число ожидающих броней этого репетитора.
Контейнер в `sidebar.html` сам запрашивает эндпоинт (`hx-trigger="load"`)
и перечитывает его по `slot-saved`: успешные подтверждение, отклонение и
отмена шлют это событие с любой страницы (тот же приём, что у баннера
`/tutor/notices`).

Ноль ожидающих — пустое тело: контейнер остаётся без кружка, ноль не
сигнал к действию.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.booking.services.access import require_tutor_id
from app.booking.services.booking_list import pending_count
from app.database import get_db

router = APIRouter()

BOOKINGS_URL = "/tutor/bookings"


@router.get(f"{BOOKINGS_URL}/count", response_class=HTMLResponse)
def bookings_count_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Число необработанных заявок; без сессии — редирект на вход."""
    count = pending_count(db, tutor_id)
    return HTMLResponse(content=str(count) if count else "")
