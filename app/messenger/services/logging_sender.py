"""Декоратор-обёртка «журнал отправки» — наращивает Sender логированием."""

import logging

from app.messenger.services.errors import SendError
from app.messenger.services.sender import Sender

logger = logging.getLogger(__name__)


class LoggingSender:
    """Пишет в журнал результат отправки, не зная о конкретном мессенджере.

    Декоратор по GoF: хранит обёрнутый `Sender` и повторяет его
    интерфейс. Имя мессенджера передаётся подписью — журналу оно нужнее,
    чем объекту отправки.
    """

    def __init__(self, inner: Sender, messenger: str) -> None:
        self._inner = inner
        self._messenger = messenger

    def send(self, config: str, recipient: str, text: str) -> None:
        try:
            self._inner.send(config, recipient, text)
        except SendError:
            # Получателя не логируем целиком: chat_id — персональные данные.
            logger.warning(
                "Отправка в %s не удалась (получатель …%s)",
                self._messenger, recipient[-4:],
            )
            raise
        logger.info("Отправлено в %s (получатель …%s)", self._messenger, recipient[-4:])
