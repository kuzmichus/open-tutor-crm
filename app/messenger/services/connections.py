"""Статусы подключения репетитора к мессенджерам.

«Подключён» = в параметрах репетитора лежит непустой токен
(`telegram_token`, …). Сетевой проверки нет: страница настроек должна
рендериться без доступа в сеть, реальная валидность токена проявится
при первой отправке.
"""

from sqlalchemy.orm import Session

from app.messenger.services.messengers import MESSENGERS, token_key
from app.tutor.services.params import all_params, get_param


def is_messenger_connected(db: Session, tutor_id: str, messenger: str) -> bool:
    """Подключён ли репетитор к конкретному мессенджеру.

    Неизвестное имя мессенджера — «не подключён», а не ошибка: вопрос
    факта, а не валидации.
    """
    if messenger not in MESSENGERS:
        return False
    return bool(get_param(db, tutor_id, token_key(messenger)))


def connected_messengers(db: Session, tutor_id: str) -> list[str]:
    """Список мессенджеров, к которым подключён репетитор.

    Один запрос за всеми параметрами (без N запросов на мессенджер),
    порядок — закрытый список `MESSENGERS`.
    """
    params = all_params(db, tutor_id)
    return [
        messenger
        for messenger in MESSENGERS
        if params.get(token_key(messenger))
    ]
