"""Представление данных рассылок для шаблонов (чистые функции без БД/HTTP).

Подписи, зависящие от педагога (даты), не дублируются: `operation_datetime`
финансов и `next_lesson_label` учеников уже зарегистрированы шаблону.
"""

from app.messenger.services.messengers import MESSENGER_LABELS


def messenger_label(messenger: str) -> str:
    """Человекочитаемая подпись мессенджера (неизвестный — как есть)."""
    return MESSENGER_LABELS.get(messenger, messenger)


def recipients_count_label(count: int) -> str:
    """«Будет отправлено N пользователям» с согласованием дательного падежа."""
    if count % 10 == 1 and count % 100 != 11:
        ending = "пользователю"
    else:
        ending = "пользователям"
    return f"Будет отправлено {count} {ending}"


def delivery_summary_label(summary: dict) -> str:
    """Сводка успешной отправки одной строкой («доставлено сообщений: N»).

    Формулировки без склонения числительных: «сообщений: 3» читается
    одинаково при любом значении.
    """
    parts = [
        f"Доставлено сообщений: {summary.get('delivered', 0)}",
        f"с ошибками: {summary.get('failed', 0)}",
        f"пропущено без каналов: {summary.get('skipped', 0)}",
    ]
    return ", ".join(parts)


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        messenger_label=messenger_label,
        recipients_count_label=recipients_count_label,
        delivery_summary_label=delivery_summary_label,
    )
