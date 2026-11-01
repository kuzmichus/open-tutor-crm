"""OAuth 2.0 с Google: ссылка согласия, обмен кода, обновление токена.

Креды (client_id/client_secret) задаёт владелец сервера в окружении —
репетитор их не вводит (design D1). HTTP — stdlib `urllib`, как у
`app/messenger/services/telegram_bot_api.py`: новая зависимость ради
двух POST-запросов не нужна.

Обмен кода и обновление токена идут с **одним и тем же**
`redirect_uri`, который был в ссылке согласия, иначе Google отвергает
запрос (`redirect_uri_mismatch`) — поэтому адрес строит один сервис
(`redirect.py`) и передаёт сюда параметром.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from app.config import settings
from app.gcalendar.services.errors import (
    GoogleApiError,
    GoogleNotConfigured,
    GoogleReauthRequired,
)

# Таймаут ограничен: вызов синхронный и не должен подвешивать запрос.
TIMEOUT_SECONDS = 10

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Доступ к событиям календаря + минимальные данные аккаунта для подписи
# «Календарь подключён (email)» в карточке.
SCOPE = "https://www.googleapis.com/auth/calendar.events openid email"

# `invalid_grant` — коды ответа, означающие «токен больше не действует»:
# пользователь отозвал доступ или refresh_token устарел. Повторять запрос
# бессмысленно, нужно повторное подключение (design D10).
_REAUTH_ERRORS = {"invalid_grant", "invalid_token", "unauthorized_client"}

def configured() -> bool:
    """Креды OAuth заданы в окружении сервера (иначе интеграция выключена)."""
    return bool(settings.google_client_id and settings.google_client_secret)

def _require_configured() -> None:
    if not configured():
        raise GoogleNotConfigured(
            "Google Календарь не настроен на сервере: задайте "
            "GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET."
        )

def build_auth_url(redirect_uri: str, state: str) -> str:
    """Ссылка согласия Google: offline-доступ и одноразовый `state`.

    `access_type=offline` нужен ради refresh_token (без него Google
    выдаёт только часовой access_token), `prompt=consent` — чтобы
    refresh_token пришёл и при повторном подключении: без него Google
    отдаёт его только при первом согласии, и после «Отключить» токена
    бы не было вовсе.
    """
    _require_configured()
    query = urllib.parse.urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    })
    return f"{AUTH_URL}?{query}"

def exchange_code(code: str, redirect_uri: str) -> dict:
    """Обменивает код согласия на токены; возвращает тело ответа Google."""
    _require_configured()
    return _token_request({
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })

def refresh_access_token(refresh_token: str) -> dict:
    """Новый access_token по refresh_token; при `invalid_grant` — повторный вход."""
    _require_configured()
    return _token_request({
        "refresh_token": refresh_token,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "grant_type": "refresh_token",
    })

def revoke_token(token: str) -> None:
    """Отзывает токен в Google (best-effort: ошибка не считается провалом).

    Отзыв — вежливость, а не условие отключения: локальные токены
    удаляются в любом случае, иначе «Отключить» не работало бы при
    недоступном Google.
    """
    if not token or not configured():
        return
    body = urllib.parse.urlencode({"token": token}).encode()
    request = urllib.request.Request(REVOKE_URL, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            return
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return

def fetch_account_email(access_token: str) -> str:
    """Email аккаунта для подписи карточки; пустая строка — не удалось.

    Это подпись, а не данные: недоступность userinfo не должна ломать
    подключение календаря.
    """
    request = urllib.request.Request(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return ""
    return str(body.get("email") or "")

def _token_request(payload: dict) -> dict:
    """POST на token endpoint; ошибка Google → доменное исключение."""
    body = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # Google описывает причину в теле (`error`, `error_description`).
        code, description = _error_body(exc.read())
        if code in _REAUTH_ERRORS:
            raise GoogleReauthRequired(
                "Google: доступ отозван, подключите календарь заново."
            ) from exc
        raise GoogleApiError(
            f"Google: {description or code or exc.code}"
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise GoogleApiError("Google: сеть недоступна.") from exc
    except ValueError as exc:
        raise GoogleApiError("Google: некорректный ответ сервера.") from exc

def _error_body(raw: bytes) -> tuple[str, str]:
    """`(error, error_description)` из тела ответа; без тела — пустые строки."""
    try:
        body = json.loads(raw)
    except (ValueError, AttributeError):
        return "", ""
    return str(body.get("error") or ""), str(body.get("error_description") or "")
