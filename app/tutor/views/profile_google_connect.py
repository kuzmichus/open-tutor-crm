"""Начало подключения Google Календаря: `GET /tutor/profile/google/connect`.

GET, а не POST, потому что действие — переход на внешний сайт согласия
Google: браузер должен открыть его обычной навигацией (POST-переход на
чужой домен браузеры показывают предупреждением). Состояние при этом не
меняется: сохраняется только одноразовый `state`, а сам доступ появится
лишь после callback с кодом от Google.

Без кредов в окружении сервера подключение не начинается: репетитор
возвращается на вкладку с подсказкой, что именно задать владельцу
сервера (design D1).
"""

import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.gcalendar.services import connection, oauth
from app.gcalendar.services.redirect import redirect_uri
from app.tutor.models.tutor import Tutor

router = APIRouter()

TAB_URL = "/tutor/profile?tab=calendar"

# Длина `state`: 32 символа base64url — достаточно против подбора,
# влезает в URL без проблем.
STATE_BYTES = 24

@router.get("/tutor/profile/google/connect")
def connect_google(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Готовит `state` и уводит на страницу согласия Google."""
    if db.get(Tutor, tutor_id) is None:
        raise LoginRequired()
    if not oauth.configured():
        return RedirectResponse(
            f"{TAB_URL}&google_error=not_configured", status_code=303
        )

    state = secrets.token_urlsafe(STATE_BYTES)
    connection.save_oauth_state(db, tutor_id, state)
    return RedirectResponse(
        oauth.build_auth_url(redirect_uri(request), state), status_code=303
    )
