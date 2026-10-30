"""Разбор формы «Настройки уведомлений» (вкладка «Уведомления»).

Чекбоксы не отмеченных значений в форме не присылают — отсутствие
флага означает «выключено». Оффсеты напоминаний приходят списком
(мультивыбор) и фильтруются по закрытому набору REMINDER_OFFSETS.
"""

import re

from app.common.services.forms import int_or_none
from app.tutor.models.tutor_settings import REMINDER_OFFSETS

# Время «ЧЧ:ММ»: input[type=time] присылает именно такой формат,
# но ручной ввод подменой формы — тоже валидируем.
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Переключатели вкладки: имя поля формы = имя колонки модели.
TOGGLE_FIELDS = (
    "notify_lesson_reminder",
    "notify_lesson_confirmation",
    "notify_daily_digest",
    "notify_cancellation",
    "notify_homework",
    "notify_debtors_weekly",
    "notify_low_balance",
    "notify_insufficient_funds",
    "notify_birthday",
)


def parse_notifications_form(form: dict) -> tuple[dict | None, list[str]]:
    """Разбирает форму уведомлений: (значения для записи, ошибки)."""
    errors: list[str] = []

    values: dict = {name: bool(form.get(name)) for name in TOGGLE_FIELDS}

    # Оффсеты: форма присылает строки-минуты; вне закрытого набора —
    # отбрасываем (не ошибка: подменённая форма не должна рушить сохранение).
    raw_offsets = form.get("reminder_offsets") or []
    if isinstance(raw_offsets, str):
        raw_offsets = [raw_offsets]
    picked = {
        minutes
        for raw in raw_offsets
        if (minutes := int_or_none(raw)) in REMINDER_OFFSETS
    }
    values["reminder_offsets"] = [
        offset for offset in REMINDER_OFFSETS if offset in picked
    ]

    digest_time = (form.get("digest_time") or "").strip()
    if not _TIME_RE.match(digest_time):
        errors.append("Время отправки сводки — в формате ЧЧ:ММ.")
    else:
        values["digest_time"] = digest_time

    threshold = int_or_none((form.get("low_balance_threshold") or "").strip())
    if threshold is None or threshold < 0:
        errors.append("Порог низкого баланса — целое число не меньше нуля.")
    else:
        values["low_balance_threshold"] = threshold

    if errors:
        return None, errors
    return values, []
