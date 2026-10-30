"""Отправитель MAX: Bot API `POST /messages` на stdlib `urllib`."""

import json
import urllib.error
import urllib.parse
import urllib.request

from app.messenger.services.errors import SendError
from app.messenger.services.registry import register_sender
from app.messenger.services.tls_context import api_ssl_context

# Таймаут ограничен: отправка синхронная и не должна подвешивать запрос.
_TIMEOUT_SECONDS = 10


@register_sender("max")
class MaxSender:
    """Доставляет сообщение через Bot API MAX (документация: dev.max.ru).

    `config` — токен бота, `recipient` — chat_id чата или канала
    (int64 строкой). Личные диалоги адресуются `user_id`, а не
    `chat_id` — адресация по пользователю пока не поддерживается,
    расширить можно разбором префикса получателя.

    Токен передаётся сырой строкой в заголовке `Authorization` (без
    `Bearer` — API вернёт 401 «No access token»); query-параметр
    `access_token` устарел. Базовый домен — `platform-api2.max.ru`:
    старые `botapi`/`platform-api` отключаются в 2026 году.
    """

    _API_URL = "https://platform-api2.max.ru/messages"

    def send(self, config: str, recipient: str, text: str) -> None:
        url = f"{self._API_URL}?{urllib.parse.urlencode({'chat_id': recipient})}"
        payload = json.dumps({"text": text}).encode()
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": config,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=_TIMEOUT_SECONDS, context=api_ssl_context()
            ) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise SendError(
                f"MAX: {_error_description(exc.read()) or exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise SendError(f"MAX: сеть недоступна ({exc.reason})") from exc

        # Успех — 200 с объектом отправленного сообщения.
        if not body.get("message"):
            raise SendError("MAX: неожиданный ответ API")


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
