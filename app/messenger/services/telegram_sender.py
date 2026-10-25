"""Отправитель Telegram: Bot API `sendMessage` на stdlib `urllib`."""

import json
import urllib.error
import urllib.request

from app.messenger.services.errors import SendError
from app.messenger.services.registry import register_sender
from app.messenger.services.sender import Sender

# Таймаут ограничен: отправка синхронная и не должна подвешивать запрос.
_TIMEOUT_SECONDS = 10


@register_sender("telegram")
class TelegramSender:
    """Доставляет сообщение через Bot API (документация: core.telegram.org).

    `config` — токен бота, `recipient` — chat_id (число строкой) или
    `@username` канала. Установленной библиотеки нет, а это единственный
    запрос на отправку — обходится штатным `urllib` без новых зависимостей.
    """

    _API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def send(self, config: str, recipient: str, text: str) -> None:
        url = self._API_URL.format(token=config)
        payload = json.dumps({"chat_id": recipient, "text": text}).encode()
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # Telegram описывает ошибку в теле ответа — покажем её, а не код.
            raise SendError(
                f"Telegram: {_error_description(exc.read()) or exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise SendError(f"Telegram: сеть недоступна ({exc.reason})") from exc

        if not body.get("ok"):
            raise SendError(
                f"Telegram: {body.get('description') or 'неизвестная ошибка API'}"
            )


def _error_description(raw: bytes) -> str:
    """Описание ошибки из тела HTTP-ответа; без тела — пустая строка."""
    try:
        return json.loads(raw).get("description") or ""
    except (ValueError, AttributeError):
        return ""
