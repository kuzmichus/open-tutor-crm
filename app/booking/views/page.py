"""Страница «Брони и заявки»: ожидающие решения и история.

`GET /tutor/bookings` — полный рендер списка и заголовка с публичной
ссылкой на запись. Сам список живёт в партиале `/tutor/bookings/list`:
после действий из диалога окна событие `slot-saved` перезапрашивает
контейнер, и карточка уходит в историю без перезагрузки страницы.

Пункт сайдбара «Брони» ведёт сюда же (маршрут `/tutor/bookings`, не
`/tutor/booking` — множественное число, как `/tutor/students` и
`/tutor/groups`).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.booking.services.access import LoginRequired, require_tutor_id
from app.booking.services.booking_list import tutor_bookings
from app.common.services.tutor_time import now_utc, today_local
from app.database import get_db
from app.slot.services.public_link import public_url
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

BOOKINGS_URL = "/tutor/bookings"


@router.get(BOOKINGS_URL, response_class=HTMLResponse)
def bookings_page(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Брони вошедшего репетитора; без сессии — редирект на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        raise LoginRequired()

    # Публичная ссылка на текущую неделю: `public_url` сам нормализует
    # любую дату к понедельнику, поэтому «сегодня» достаточно.
    share_url = public_url(tutor_id, today_local(tutor))

    return templates.TemplateResponse(
        request,
        "booking/index.html",
        {
            "active_page": "bookings",
            "user_name": tutor.name,
            "user_role": "Владелец",
            "tutor": tutor,
            "share_url": share_url,
            "bookings": tutor_bookings(db, tutor_id, tutor, now=now_utc()),
        },
    )
