"""Отображение кабинета: подписи дат, статусов ДЗ и значка ДЗ в календаре.

Чистые функции без БД и HTTP (как `app/lesson/services/presentation.py`).
Даты — в зоне репетитора (спека student-cabinet: зона ученика появится
с вкладкой «Профиль»), месяц — полностью, родительный падеж: «урок
30 октября 2026», «Срок: 30 октября 2026, 12:00» — форматы макета
вкладки, их не даёт короткий набор `presentation.py` уроков («окт.»).

Значок ДЗ в карточке календаря (`homework_badge_class`/`_label`) —
тот же закрытый список статусов, что у чипа вкладки «Домашние задания»:
цвет значка кодирует статус, подпись уходит в `title`/`aria-label`.
"""

from datetime import datetime

from app.common.services.tutor_time import to_local
from app.homework.models.homework import HOMEWORK_STATUS_LABELS

# Полные названия месяцев в родительном падеже — формат макета вкладки.
_MONTHS_FULL_GEN = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

# Модификатор чипа статуса: «Задано» — нейтральное, «Сдано» — работа
# отправлена, «Проверено» — финальное зелёное, «Не выполнено» — тревожное.
_HOMEWORK_CHIPS = {
    "assigned": "chip--hw-assigned",
    "submitted": "chip--hw-submitted",
    "checked": "chip--hw-checked",
    "not_done": "chip--hw-not-done",
}

# Модификатор значка ДЗ в карточке календаря: цвет кодирует статус —
# «Задано» нейтральное, «Сдано» акцентное, «Проверено» зелёное,
# «Не выполнено» тревожное. Отдельный набор классов, а не чипы: значок
# в карточке урока размером с иконку, плашка статуса там не помещается.
_HOMEWORK_BADGES = {
    "assigned": "cal-hw-badge--assigned",
    "submitted": "cal-hw-badge--submitted",
    "checked": "cal-hw-badge--checked",
    "not_done": "cal-hw-badge--not_done",
}


def _local_parts(value: datetime, tutor) -> datetime:
    """Значение из БД в настенном времени зоны педагога."""
    return to_local(value, tutor)


def homework_lesson_title(lesson, tutor) -> str:
    """«урок 30 октября 2026» — заголовок карточки ДЗ (формат макета)."""
    if lesson is None or lesson.starts_at is None:
        return "урок"
    local = _local_parts(lesson.starts_at, tutor)
    return f"урок {local.day} {_MONTHS_FULL_GEN[local.month - 1]} {local.year}"


def homework_due_label(value: datetime | None, tutor) -> str:
    """«30 октября 2026, 12:00» — строка «Срок: …» карточки."""
    if value is None:
        return ""
    local = _local_parts(value, tutor)
    return (
        f"{local.day} {_MONTHS_FULL_GEN[local.month - 1]} {local.year}, "
        f"{local.strftime('%H:%M')}"
    )


def homework_status_label(status: str) -> str:
    """Подпись статуса ДЗ: «Задано»; неизвестное значение — как есть."""
    return HOMEWORK_STATUS_LABELS.get(status, status)


def homework_chip_class(status: str) -> str:
    """Класс чипа статуса: «chip--hw-assigned»; неизвестное — нейтральный."""
    return _HOMEWORK_CHIPS.get(status, "chip--hw-assigned")


def homework_badge_class(status: str) -> str:
    """Класс значка ДЗ в карточке календаря; неизвестный статус — «Задано».

    Цвет — единственный носитель смысла значка, поэтому класс задаётся
    сервером по закрытому списку статусов, а не вычисляется в шаблоне.
    """
    return _HOMEWORK_BADGES.get(status, "cal-hw-badge--assigned")


def homework_badge_label(status: str) -> str:
    """Подпись значка ДЗ для `title`/`aria-label`: «Задано», «Проверено»…"""
    return homework_status_label(status)


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        homework_lesson_title=homework_lesson_title,
        homework_due_label=homework_due_label,
        homework_status_label=homework_status_label,
        homework_chip_class=homework_chip_class,
        homework_badge_class=homework_badge_class,
        homework_badge_label=homework_badge_label,
    )
