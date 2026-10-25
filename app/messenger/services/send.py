"""Отправка сообщения в мессенджер: диспетчер над реестром отправителей.

Собирает цепочку декораторов `LoggingSender(RetrySender(Concrete()))`:
реестр выбирает конкретного отправителя, обёртки добавляют журнал и
повтор. Ошибки возвращаются списком строк (соглашение сервисов проекта),
`SendError` наружу не выходит.
"""

from sqlalchemy.orm import Session

from app.messenger.services.connections import is_messenger_connected
from app.messenger.services.errors import SendError
from app.messenger.services.logging_sender import LoggingSender
from app.messenger.services.messengers import MESSENGER_LABELS, MESSENGERS, token_key
from app.messenger.services.registry import get_sender_class
from app.messenger.services.retry_sender import RetrySender
from app.tutor.services.params import get_param

# Регистрация отправителей: импорт выполняет декораторы @register_sender.
from app.messenger.services import max_sender  # noqa: F401
from app.messenger.services import telegram_sender  # noqa: F401


def send_message(
    db: Session,
    tutor_id: str,
    messenger: str,
    recipient: str,
    text: str,
) -> list[str]:
    """Отправляет текст получателю через указанный мессенджер.

    Возвращает список ошибок: пустой список — сообщение доставлено.
    Токен берётся из параметров репетитора; из формы/запроса
    `tutor_id` приходить не должен (см. правила доступа).
    """
    if messenger not in MESSENGERS:
        return [f"Неизвестный мессенджер: {messenger}."]
    label = MESSENGER_LABELS[messenger]

    sender_class = get_sender_class(messenger)
    if sender_class is None:
        return [f"Отправка в {label} пока не поддерживается."]

    if not recipient or not recipient.strip():
        return ["Не указан получатель сообщения."]
    if not text or not text.strip():
        return ["Пустой текст сообщения."]

    if not is_messenger_connected(db, tutor_id, messenger):
        return [f"Мессенджер {label} не подключён — укажите токен в настройках."]
    config = get_param(db, tutor_id, token_key(messenger))

    sender = LoggingSender(RetrySender(sender_class()), messenger=label)
    try:
        sender.send(config, recipient.strip(), text.strip())
    except SendError as exc:
        return [str(exc)]
    return []
