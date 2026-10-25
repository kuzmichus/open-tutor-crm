"""Базовый интерфейс отправителя — компонент паттерна «декоратор»."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Sender(Protocol):
    """Умеет доставить сообщение одним вызовом.

    `config` — секрет отправителя, как он хранится в параметрах
    репетитора (для Telegram — токен бота). Конкретные отправители
    регистрируются в реестре (`app.messenger.services.registry`), а
    обёртки-декораторы (`LoggingSender`, `RetrySender`) принимают любой
    `Sender` и наращивают поведение, не зная о конкретном мессенджере.
    """

    def send(self, config: str, recipient: str, text: str) -> None:
        """Доставляет сообщение; неудача — `SendError`."""
        ...
