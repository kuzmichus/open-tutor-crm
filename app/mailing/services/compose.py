"""Контекст вкладки «Новое сообщение»: получатели + шаблоны композера.

Собирает всё, что нужно обеим колонкам формы рассылки, одним набором
запросов. Текст выбранного шаблона клиент берёт из `data-text` опции
селекта — отдельный JSON не нужен.
"""

from sqlalchemy.orm import Session

from app.mailing.services.recipients import (
    SEGMENT_LABELS,
    SEGMENTS,
    list_recipients,
    normalize_segment,
)
from app.mailing.services.rendering import PLACEHOLDERS
from app.mailing.services.templates import list_templates
from app.messenger.services.messengers import SUPPORTED


def compose_context(db: Session, tutor_id: str, *, q: str, segment: str) -> dict:
    """Данные формы рассылки: карточки получателей, сегменты, шаблоны."""
    chosen = normalize_segment(segment)
    recipients = list_recipients(db, tutor_id, q=q, segment=chosen)
    templates = list_templates(db, tutor_id)

    return {
        "recipients": recipients,
        "q": q,
        "segment": chosen,
        "segments": [
            {"key": key, "label": SEGMENT_LABELS[key], "active": key == chosen}
            for key in SEGMENTS
        ],
        "channels_list": list(SUPPORTED),
        "templates": templates,
        "placeholders": PLACEHOLDERS,
        # Панель текста: на странице поле пустое, ввод живёт в Alpine.
        "form_text": "",
        "send_summary": None,
        "send_errors": [],
    }
