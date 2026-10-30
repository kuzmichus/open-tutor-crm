"""Чтение данных бота Telegram для привязки канала: getMe и getUpdates.

Отправка — в `telegram_sender.py`; здесь только «приёмная сторона»
привязки: ник бота для диплинка и апдейты для подтверждения кода.
"""

import json
import urllib.error
import urllib.request

from app.messenger.services.errors import BotApiError
from app.messenger.services.tls_context import api_ssl_context

# Таймаут ограничен: вызов синхронный и не должен подвешивать запрос.
_TIMEOUT_SECONDS = 10

_API_URL = "https://api.telegram.org/bot{token}/{method}"


def bot_username(token: str) -> str:
    """Имя пользователя бота (без `@`) из getMe — для диплинка."""
    result = _call(token, "getMe") or {}
    username = result.get("username") or ""
    if not username:
        raise BotApiError("Telegram: у бота нет имени пользователя")
    return username


def pending_updates(token: str) -> list[dict]:
    """Апдейты бота (getUpdates без offset).

    Очередь не подтверждается offset'ом, поэтому повторные проверки видят
    старые апдейты — поиск кода обязан быть устойчивым к дублям (код
    одноразовый, сравнение точное).
    """
    return _call(token, "getUpdates") or []


def _call(token: str, method: str) -> dict:
    """GET-запрос к Bot API; `ok: false` и сетевые ошибки — `BotApiError`."""
    url = _API_URL.format(token=token, method=method)
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(
            request, timeout=_TIMEOUT_SECONDS, context=api_ssl_context()
        ) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # Telegram описывает ошибку в теле ответа — покажем её, а не код.
        raise BotApiError(
            f"Telegram: {_error_description(exc.read()) or exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise BotApiError(f"Telegram: сеть недоступна ({exc.reason})") from exc

    if not body.get("ok"):
        raise BotApiError(
            f"Telegram: {body.get('description') or 'неизвестная ошибка API'}"
        )
    return body.get("result")


def _error_description(raw: bytes) -> str:
    """Описание ошибки из тела HTTP-ответа; без тела — пустая строка."""
    try:
        return json.loads(raw).get("description") or ""
    except (ValueError, AttributeError):
        return ""
