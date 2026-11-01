"""Callback Google OAuth: `GET /tutor/profile/google/callback`.

Google возвращает сюда `code` (согласие дано) либо `error` (отказ).
Порядок проверок важен:

1. `state` сверяется с сохранённым и **гасится** — второй callback с тем
   же значением отклоняется. Это защита от подмены запроса (CSRF):
   чужой код не привяжется к аккаунту репетитора;
2. `error=access_denied` — репетитор отказал: редирект с подсказкой, без
   сохранения токенов;
3. обмен кода на токены — с **тем же** `redirect_uri`, что был в ссылке
   согласия, иначе Google отвечает `redirect_uri_mismatch`;
4. сохранение токенов, email аккаунта и id календаря;
5. первичная выгрузка будущих занятий (ответ пользователя на вопрос №2).

Ошибка обмена не оставляет полуподключения: токены сохраняются только
после успешного ответа Google.
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.gcalendar.services import connection, initial_sync, oauth
from app.gcalendar.services.errors import GoogleError
from app.gcalendar.services.redirect import redirect_uri
from app.tutor.models.tutor import Tutor

router = APIRouter()

logger = logging.getLogger("gcalendar")

TAB_URL = "/tutor/profile?tab=calendar"

@router.get("/tutor/profile/google/callback")
def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Завершает подключение: токены, email аккаунта, выгрузка занятий."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    # Одноразовость: `take_oauth_state` читает и удаляет значение, поэтому
    # повторный запрос с тем же `state` доходит до этой строки с пустым
    # ожидаемым значением и отклоняется.
    expected = connection.take_oauth_state(db, tutor_id)
    if not expected or not state or state != expected:
        return RedirectResponse(f"{TAB_URL}&google_error=state", status_code=303)

    if error:
        # `access_denied` и прочие отказы: токенов нет, подключать нечего.
        return RedirectResponse(f"{TAB_URL}&google_error=denied", status_code=303)
    if not code:
        return RedirectResponse(f"{TAB_URL}&google_error=exchange", status_code=303)

    try:
        tokens = oauth.exchange_code(code, redirect_uri(request))
    except GoogleError as exc:
        logger.warning("Google Календарь: обмен кода не удался: %s", exc)
        return RedirectResponse(f"{TAB_URL}&google_error=exchange", status_code=303)

    access = str(tokens.get("access_token") or "")
    if not access:
        return RedirectResponse(f"{TAB_URL}&google_error=exchange", status_code=303)

    connection.save_tokens(
        db,
        tutor_id,
        refresh_token=tokens.get("refresh_token"),
        access_token=access,
        expires_in=tokens.get("expires_in"),
        account_email=oauth.fetch_account_email(access),
    )

    # Первичная выгрузка — сразу после подключения (ответ на вопрос №2).
    # Ошибки Google уже пойманы внутри синхронизации: подключение
    # состоялось, даже если часть занятий не выгрузилась — сверка догонит.
    initial_sync.sync_upcoming(db, tutor)

    return RedirectResponse(f"{TAB_URL}&saved=1", status_code=303)
