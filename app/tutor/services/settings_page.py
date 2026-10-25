"""Контекст страницы настройки мессенджеров (`/tutor/settings`).

Строится по образцу контекста `/tutor/profile`: вкладки через `?tab=`,
один строитель на GET и на ре-рендер с ошибками. Пока вкладка одна —
«Мессенджеры»; структура не отличается от страницы с четырьмя.
"""

from sqlalchemy.orm import Session

from app.messenger.services.connections import is_messenger_connected
from app.messenger.services.messengers import (
    MESSENGERS,
    MESSENGER_HINTS,
    MESSENGER_LABELS,
    MESSENGER_PLACEHOLDERS,
    SUPPORTED,
    token_key,
)
from app.tutor.models.tutor import Tutor
from app.tutor.services.params import get_param

# Вкладки страницы: ключ в URL → подпись таба. Порядок — порядок табов.
TABS = (
    ("messengers", "Мессенджеры"),
)

TAB_KEYS = tuple(key for key, _label in TABS)

# Каждая форма знает свой POST-адрес: шаблону не нужно строить пути.
TAB_ACTIONS = {
    "messengers": "/tutor/settings/messengers",
}


def normalize_tab(raw: str | None) -> str:
    """Ключ вкладки из query-параметра; неизвестное значение — первая вкладка."""
    return raw if raw in TAB_KEYS else TAB_KEYS[0]


def _form_defaults(db: Session, tutor_id: str) -> dict[str, str]:
    """Значения полей формы из сохранённых токенов (отсутствующий — пустой)."""
    return {
        token_key(messenger): get_param(db, tutor_id, token_key(messenger)) or ""
        for messenger in SUPPORTED
    }


def _messenger_sections(db: Session, tutor_id: str) -> list[dict]:
    """Секции вкладки: по элементу на мессенджер закрытого списка."""
    sections = []
    for messenger in MESSENGERS:
        available = messenger in SUPPORTED
        sections.append({
            "key": messenger,
            "label": MESSENGER_LABELS[messenger],
            # Недоступные пока мессенджеры рисуются без поля ввода.
            "available": available,
            "connected": is_messenger_connected(db, tutor_id, messenger),
            "hint": MESSENGER_HINTS.get(messenger, ""),
            "placeholder": MESSENGER_PLACEHOLDERS.get(messenger, ""),
        })
    return sections


def settings_page_context(
    db: Session,
    tutor: Tutor,
    tab: str,
    saved: bool = False,
    errors: list[str] | None = None,
    form: dict | None = None,
) -> dict:
    """Контекст шаблона настроек: вкладки, секции мессенджеров и форма."""
    tab = normalize_tab(tab)
    return {
        "active_page": "settings",
        "user_name": tutor.name,
        "user_role": "Владелец",
        "tutor": tutor,
        "tab": tab,
        "tabs": TABS,
        "action": TAB_ACTIONS[tab],
        "saved": saved,
        "errors": errors or [],
        "form": form if form is not None else _form_defaults(db, tutor.id),
        "messengers": _messenger_sections(db, tutor.id),
    }
