"""История сообщений бота: данные для вкладки «История».

Чтение журнала — общий `messenger.history` (он пишет и другие исходящие,
кроме рассылок); здесь только представление строк для шаблона.
"""

from sqlalchemy.orm import Session

from app.messenger.services.history import list_messages
from app.messenger.services.messengers import MESSENGER_LABELS

# Сколько последних записей показывает вкладка (v1 — без постраничности).
HISTORY_LIMIT = 100


def list_history(db: Session, tutor_id: str) -> list[dict]:
    """Строки журнала: запись, имя ученика и подписи для шаблона."""
    rows = list_messages(db, tutor_id, limit=HISTORY_LIMIT)
    return [
        {
            "message": message,
            "student_name": name,
            "messenger_label": MESSENGER_LABELS.get(message.messenger, message.messenger),
            "status_label": "Доставлено" if message.status == "sent" else "Ошибка",
            "is_error": message.status == "error",
        }
        for message, name in rows
    ]
