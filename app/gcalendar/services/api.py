"""REST-клиент Google Calendar API v3: события урока.

Только то, что нужно интеграции: создать событие, изменить его,
удалить и прочитать список событий календаря для сверки. HTTP — stdlib
`urllib` с таймаутом, как у клиентов мессенджеров: новая зависимость
ради четырёх запросов не нужна.

Авторизация — заголовок `Authorization: Bearer <access_token>`. Истёкший
токен API встречает 401: клиент один раз просит свежий токен у
вызывающей стороны (`refresh` — callable) и повторяет запрос. Второй 401
подряд — уже ошибка, бесконечного цикла нет (design D6).

Удаление 404/410 считается успехом: событие уже удалено (руками в
Google или предыдущим прогоном) — цель достигнута, повторять нечего.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from app.gcalendar.services.errors import GoogleApiError, GoogleUnauthorized

TIMEOUT_SECONDS = 10

API_ROOT = "https://www.googleapis.com/calendar/v3/calendars"

# `sendUpdates=none`: Google не рассылает участникам письма о событии —
# события создаются без приглашений, участники не приглашаются.
_NO_NOTIFY = "sendUpdates=none"

Refresh = Callable[[], str | None]

def insert_event(access_token: str, calendar_id: str, payload: dict) -> str:
    """Создаёт событие и возвращает его id."""
    body = _request(
        "POST",
        _events_url(calendar_id),
        access_token,
        payload=payload,
        query=_NO_NOTIFY,
    )
    event_id = str(body.get("id") or "")
    if not event_id:
        raise GoogleApiError("Google: сервис не вернул id события.")
    return event_id

def patch_event(
    access_token: str,
    calendar_id: str,
    event_id: str,
    payload: dict,
) -> None:
    """Частично обновляет событие: меняются только присланные поля."""
    _request(
        "PATCH",
        _event_url(calendar_id, event_id),
        access_token,
        payload=payload,
        query=_NO_NOTIFY,
    )

def delete_event(access_token: str, calendar_id: str, event_id: str) -> None:
    """Удаляет событие; 404/410 — событие уже удалено, это не ошибка."""
    try:
        _request(
            "DELETE",
            _event_url(calendar_id, event_id),
            access_token,
            query=_NO_NOTIFY,
        )
    except _NotFound:
        return

def list_event_ids(
    access_token: str,
    calendar_id: str,
    *,
    time_min: str,
    time_max: str,
) -> set[str]:
    """Id всех событий календаря в окне [time_min, time_max) — для сверки.

    Читаются только id (`fields=items(id)`): сверке нужен состав
    событий, а не их содержимое — экономит трафик и квоту.
    """
    ids: set[str] = set()
    page_token = ""
    while True:
        query = {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "false",
            "maxResults": "2500",
            "fields": "items(id),nextPageToken",
        }
        if page_token:
            query["pageToken"] = page_token
        body = _request(
            "GET",
            _events_url(calendar_id),
            access_token,
            query=urllib.parse.urlencode(query),
        )
        for item in body.get("items") or []:
            event_id = str(item.get("id") or "")
            if event_id:
                ids.add(event_id)
        page_token = str(body.get("nextPageToken") or "")
        if not page_token:
            return ids

class _NotFound(GoogleApiError):
    """404/410 от API: событие уже удалено (внутреннее, наружу не выходит)."""

def _events_url(calendar_id: str) -> str:
    return f"{API_ROOT}/{urllib.parse.quote(calendar_id, safe='')}/events"

def _event_url(calendar_id: str, event_id: str) -> str:
    return f"{_events_url(calendar_id)}/{urllib.parse.quote(event_id, safe='')}"

def _request(
    method: str,
    url: str,
    access_token: str,
    *,
    payload: dict | None = None,
    query: str = "",
) -> dict:
    """Запрос к API; сеть и ошибки ответа — `GoogleApiError`."""
    if query:
        url = f"{url}?{query}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise GoogleUnauthorized("Google: токен доступа отклонён.") from exc
        if exc.code in (404, 410):
            raise _NotFound("Google: событие не найдено.") from exc
        raise GoogleApiError(
            f"Google: {_error_message(exc.read()) or exc.code}"
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise GoogleApiError("Google: сеть недоступна.") from exc

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise GoogleApiError("Google: некорректный ответ сервера.") from exc

def _error_message(raw: bytes) -> str:
    """Текст ошибки из тела ответа Google (`error.message`); без тела — пусто."""
    try:
        body = json.loads(raw)
    except (ValueError, AttributeError):
        return ""
    error = body.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "")
    return str(error or "")
