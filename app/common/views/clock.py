"""Фрагмент времени для htmx-часов.

Время показывается в зоне вошедшего педагога, без сессии — в системной
зоне сервера (design.md D7). Эндпоинт намеренно не требует входа: часы
стоят в `#clock` и запрашиваются каждую секунду, а 303 на `/tutor/login`
в фрагменте отдал бы пустое место вместо времени.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.services.tutor_time import now_utc, to_local
from app.database import get_db
from app.tutor.models.tutor import Tutor
from app.tutor.services.sessions import SessionService

router = APIRouter()

_sessions = SessionService()

_CLOCK_FORMAT = "%Y-%m-%d %H:%M:%S"


def _tutor_from_request(request: Request, db: Session) -> Tutor | None:
    """Карточка вошедшего репетитора или None (часы работают и без сессии)."""
    tutor_id = _sessions.get_tutor_id_from_request(db, request)
    return db.get(Tutor, tutor_id) if tutor_id else None


@router.get("/time", response_class=HTMLResponse)
def clock_fragment(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Отдаёт текущую дату/время в зоне педагога для `#clock` через htmx.

    Ответ остаётся фрагментом с датой в любом случае: без сессии `to_local`
    с `tutor=None` даёт системную зону сервера (design.md D2), а не редирект.
    """
    tutor = _tutor_from_request(request, db)
    return HTMLResponse(to_local(now_utc(), tutor).strftime(_CLOCK_FORMAT))