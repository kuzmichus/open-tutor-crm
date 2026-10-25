"""Разбор формы «Календарь»: часовой пояс, учебный год, уроки по умолчанию.

Кварталы хранятся строками «ММ-ДД» без года (design D6): пресеты серии
уроков подставляют ближайшую будущую дату в момент использования.
Длительность урока валидируется по закрытому списку LESSON_DURATIONS —
источник истины живёт в модуле lesson (design D7).
"""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.lesson.models.lesson import LESSON_DURATIONS

# «ММ-ДД»: месяц 01–12, день — по календарю месяца.
_QUARTER_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")

QUARTER_FIELDS = ("quarter1_end", "quarter2_end", "quarter3_end", "quarter4_end")

QUARTER_LABELS = {
    "quarter1_end": "I четверть",
    "quarter2_end": "II четверть",
    "quarter3_end": "III четверть",
    "quarter4_end": "IV четверть",
}


def _int_or_none(raw: str) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _is_valid_timezone(name: str) -> bool:
    """True, если имя распознаётся IANA TZDB (без fallback на UTC)."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return False
    return True


def parse_calendar_form(form: dict) -> tuple[dict | None, list[str]]:
    """Разбирает форму календаря: (значения для записи, ошибки)."""
    errors: list[str] = []

    timezone = (form.get("timezone") or "").strip()
    if timezone and not _is_valid_timezone(timezone):
        errors.append("Часовой пояс — выберите зону из списка.")
    if not timezone:
        errors.append("Укажите часовой пояс.")

    values: dict = {}

    for field in QUARTER_FIELDS:
        raw = (form.get(field) or "").strip()
        if not _QUARTER_RE.match(raw):
            errors.append(f"{QUARTER_LABELS[field]} — дата в формате ММ-ДД.")
        else:
            values[field] = raw

    duration = _int_or_none((form.get("default_lesson_duration") or "").strip())
    if duration not in LESSON_DURATIONS:
        errors.append("Длительность урока по умолчанию — из списка длительностей.")
    else:
        values["default_lesson_duration"] = duration

    price_raw = (form.get("default_lesson_price") or "").strip()
    if price_raw == "":
        values["default_lesson_price"] = None
    else:
        price = _int_or_none(price_raw)
        if price is None or price < 0:
            errors.append("Стоимость урока по умолчанию — целое число не меньше нуля.")
        else:
            values["default_lesson_price"] = price

    if errors:
        return None, errors

    values["timezone"] = timezone
    return values, []
