"""Чтение данных бота MAX для привязки канала: GET /me и GET /updates.

Отправка — в `max_sender.py` (там же контракт заголовка `Authorization`:
токен сырой строкой, без `Bearer`). Здесь «приёмная сторона» привязки.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from app.messenger.services.errors import BotApiError
from app.messenger.services.tls_context import api_ssl_context

# Таймаут ограничен: вызов синхронный и не должен подвешивать запрос.
_TIMEOUT_SECONDS = 10

_BASE_URL = "https://platform-api2.max.ru"

# timeout=0 обязателен: по умолчанию /updates держит long poll 30 c,
# а проверка привязки — синхронная часть HTTP-запроса страницы.
_UPDATES_TIMEOUT = 0


def bot_nickname(token: str) -> str:
    """Никнейм бота (без `@`) из GET /me — для диплинка.

    Никнейм у бота опционален, но без него диплинк не построить.
    """
    nickname = _call(token, "/me").get("username") or ""
    if not nickname:
        raise BotApiError("MAX: у бота нет никнейма — задайте его на платформе MAX")
    return nickname


def fetch_updates(token: str, marker: int | None) -> tuple[list[dict], int | None]:
    """Апдейты бота от маркера; возвращает (апдейты, новый маркер).

    Без маркера API отдаёт только последнее обновление, поэтому маркер
    хранится в параметрах репетитора и передаётся при каждой проверке.
    """
    params: dict[str, int] = {"timeout": _UPDATES_TIMEOUT}
    if marker is not None:
        params["marker"] = marker
    body = _call(token, "/updates", params)
    return body.get("updates") or [], body.get("marker")


def _call(token: str, path: str, params: dict | None = None) -> dict:
    """GET-запрос к Bot API MAX; ошибки HTTP и сети — `BotApiError`."""
    url = f"{_BASE_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=_TIMEOUT_SECONDS, context=api_ssl_context()
        ) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise BotApiError(
            f"MAX: {_error_description(exc.read()) or exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise BotApiError(f"MAX: сеть недоступна ({exc.reason})") from exc


def _error_description(raw: bytes) -> str:
    """Описание ошибки из тела HTTP-ответа; без тела — пустая строка.

    API отвечает объектом с полями «code» и «message» (наследие
    TamTam); для человека показываем «message», иначе «code».
    """
    try:
        body = json.loads(raw)
    except ValueError:
        return ""
    return body.get("message") or body.get("code") or ""
