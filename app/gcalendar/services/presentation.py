"""Контекст блока «Google Календарь» на вкладке «Календарь» профиля.

Читает только параметры репетитора и настройки окружения: сеть не
дёргается, как и `channels_block_context` у каналов уведомлений —
страница настроек не должна зависеть от доступности Google.

Состояния карточки (design D10):

- `configured=False` — креды не заданы на сервере: подсказка владельцу
  и неактивная кнопка;
- `connected=True` — календарь подключён: email аккаунта, «Отключить»;
- `connected=False` — не подключён: кнопка «Подключить Google»;
- `last_error` — текст последней ошибки синхронизации (в т.ч. «доступ
  отозван»), показывается под статусом.
"""

from sqlalchemy.orm import Session

from app.config import settings
from app.gcalendar.services import connection, oauth

# Адреса действий блока: шаблону не нужно строить пути.
CONNECT_URL = "/tutor/profile/google/connect"
DISCONNECT_URL = "/tutor/profile/google/disconnect"

# Подписи ошибок для redirect-потока без JS: точный текст ошибки живёт
# только в ответе действия, через URL его не донести — передаётся код.
ERROR_MESSAGES = {
    "not_configured": (
        "Google Календарь не настроен на сервере: задайте GOOGLE_CLIENT_ID "
        "и GOOGLE_CLIENT_SECRET."
    ),
    "denied": "Доступ к Google Календарю не предоставлен.",
    "state": (
        "Ссылка подключения устарела или уже использована — "
        "начните подключение заново."
    ),
    "exchange": (
        "Не удалось завершить подключение Google Календаря — "
        "попробуйте ещё раз."
    ),
    "failed": "Не удалось подключить Google Календарь.",
}

def google_error_message(code: str) -> str:
    """Текст ошибки по коду из query-параметра; неизвестный код — общий."""
    if not code:
        return ""
    return ERROR_MESSAGES.get(code, ERROR_MESSAGES["failed"])

def google_calendar_context(db: Session, tutor_id: str, error: str = "") -> dict:
    """Словарь состояния блока; `error` — текст из query-параметра страницы."""
    configured = oauth.configured()
    connected = connection.is_connected(db, tutor_id)
    return {
        "configured": configured,
        "connected": connected,
        "account_email": connection.account_email(db, tutor_id) if connected else "",
        "calendar_id": connection.calendar_id(db, tutor_id) if connected else "",
        # Ошибка страницы (например, отказ в доступе) важнее сохранённой:
        # её пользователь вызвал только что.
        "last_error": error or connection.last_error(db, tutor_id),
        "connect_url": CONNECT_URL,
        "disconnect_url": DISCONNECT_URL,
        # Синхронизация выключена владельцем сервера: подключение есть,
        # но события не пишутся — честно говорим об этом.
        "sync_enabled": settings.google_calendar_sync,
    }
