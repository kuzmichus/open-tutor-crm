"""Реестр отправителей: регистрация Python-декоратором, поиск по имени.

Новый мессенджер добавляется файлом с классом и декоратором
`@register_sender("<имя>")` — код отправки (`send_message`) при этом
не меняется. Модуль отправителя должен быть импортирован, чтобы
регистрация сработала (`send.py` импортирует их явно).
"""

from collections.abc import Callable

from app.messenger.services.sender import Sender

# Имя мессенджера → класс отправителя.
_REGISTRY: dict[str, type[Sender]] = {}


def register_sender(messenger: str) -> Callable[[type[Sender]], type[Sender]]:
    """Декоратор: кладёт класс отправителя в реестр под именем мессенджера."""

    def wrapper(cls: type[Sender]) -> type[Sender]:
        _REGISTRY[messenger] = cls
        return cls

    return wrapper


def get_sender_class(messenger: str) -> type[Sender] | None:
    """Класс отправителя мессенджера или `None`, если он не реализован."""
    return _REGISTRY.get(messenger)


def registered_messengers() -> tuple[str, ...]:
    """Имена мессенджеров с реализованными отправителями."""
    return tuple(_REGISTRY)
