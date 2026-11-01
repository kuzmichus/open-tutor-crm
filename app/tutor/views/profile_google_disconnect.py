"""Отключение Google Календаря: `POST /tutor/profile/google/disconnect`.

POST, а не GET: действие меняет состояние. Отключается только связь:
локальные токены и строки `calendar_events` удаляются, а созданные
события в календаре Google **остаются** — это расписание репетитора, и
стирать его без явной просьбы нельзя (design D11). Подсказка об этом
показана в карточке.

Отзыв токена в Google — best-effort: недоступность Google не мешает
отключению локально, иначе кнопка «Отключить» зависела бы от сети.
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.gcalendar.services import connection, mapping, oauth
from app.tutor.models.tutor import Tutor

router = APIRouter()

logger = logging.getLogger("gcalendar")

TAB_URL = "/tutor/profile?tab=calendar"

@router.post("/tutor/profile/google/disconnect")
def disconnect_google(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Забывает подключение: токены, состояние и связи с событиями."""
    if db.get(Tutor, tutor_id) is None:
        raise LoginRequired()

    # Отзыв — до удаления токенов: после `clear` отзывать уже нечего.
    refresh_token = connection.refresh_token(db, tutor_id)
    if refresh_token:
        oauth.revoke_token(refresh_token)

    mapping.forget_tutor(db, tutor_id)
    connection.clear(db, tutor_id)
    logger.info("Google Календарь: отключён (tutor=%s)", tutor_id)

    return RedirectResponse(TAB_URL, status_code=303)
