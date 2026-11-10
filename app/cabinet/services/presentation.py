"""Отображение кабинета: подписи дат и заголовков карточек ДЗ.

Чистые функции без БД и HTTP (как `app/lesson/services/presentation.py`).
Даты — в зоне репетитора (спека student-cabinet: зона ученика появится
с вкладкой «Профиль»), месяц — полностью, родительный падеж: «урок
30 октября 2026», «Срок: 30 октября 2026, 12:00» — форматы макета
вкладки, их не даёт короткий набор `presentation.py` уроков («окт.»).

Подписи и классы статусов ДЗ живут в домене ДЗ
(`app/homework/services/presentation.py`): их показывает и кабинет, и
календарь репетитора. Здесь они только ре-экспортируются, чтобы вьюхи
кабинета не зависели от чужого домена напрямую.
"""

from datetime import datetime

from app.common.services.tutor_time import to_local
from app.homework.services.presentation import (  # noqa: F401
    homework_badge_class,
    homework_badge_label,
    homework_chip_class,
    homework_status_label,
)

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


def register_template_helpers() -> None:
    """Регистрирует подписи дат кабинета в общем Jinja-окружении.

    Подписи и классы статусов ДЗ регистрирует домен ДЗ
    (`app/homework/services/presentation.py`): они общие с календарём.
    """
    from app.templating import templates

    templates.env.globals.update(
        homework_lesson_title=homework_lesson_title,
        homework_due_label=homework_due_label,
    )
