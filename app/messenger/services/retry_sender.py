"""Декоратор-обёртка «повтор отправки» — наращивает Sender ретраями."""

from app.messenger.services.errors import SendError
from app.messenger.services.sender import Sender


class RetrySender:
    """Повторяет неудачную отправку фиксированное число попыток.

    Декоратор по GoF: обёрнутый `Sender` вызывается до первой удачи,
    после исчерпания попыток последняя ошибка уходит наружу. Без паузы
    между попытками: сбои Bot API мгновенные (сеть/токен), а пауза
    усложнила бы тесты — при необходимости добавьте параметр.
    """

    def __init__(self, inner: Sender, attempts: int = 3) -> None:
        if attempts < 1:
            raise ValueError("attempts должен быть не меньше 1")
        self._inner = inner
        self._attempts = attempts

    def send(self, config: str, recipient: str, text: str) -> None:
        for attempt in range(1, self._attempts + 1):
            try:
                return self._inner.send(config, recipient, text)
            except SendError:
                # Последняя попытка не глушится: вызывающий должен увидеть
                # причину, по которой сообщение не доставлено.
                if attempt == self._attempts:
                    raise
