"""Отображение недоступности: подписи причин и срока (design.md D11).

Чистые функции без БД и HTTP (как `app/group/services/presentation.py`):
принимают отметку, возвращают строки для шаблона. Шаблон не форматирует
бизнес-данные сам (правило AGENTS.md).

Форматы срока:

- период с двумя датами — «26.10 – 30.10»;
- период без последнего дня — «с 26.10 — бессрочно»;
- постоянный выходной — «сб, бессрочно» / «сб, по 31.12».
"""

from datetime import date

from app.unavailability.models.unavailability import (
    REASON_LABELS,
    WEEKDAY_LABELS,
)


def format_day(value: date | None) -> str:
    """«26.10» — день и месяц отметки (год в списке не показывается)."""
    if value is None:
        return ""
    return value.strftime("%d.%m")


def format_span(mark) -> str:
    """Срок отметки одной строкой — см. форматы в docstring модуля."""
    if mark.mode == "period":
        start = format_day(mark.start_date)
        if mark.end_date is None:
            return f"с {start} — бессрочно"
        return f"{start} – {format_day(mark.end_date)}"
    weekday = weekday_label(mark.weekday)
    if mark.until_date is None:
        return f"{weekday}, бессрочно"
    return f"{weekday}, по {format_day(mark.until_date)}"


def weekday_label(weekday: int | None) -> str:
    """Подпись дня недели строчными: «сб» (в списке — не заголовок)."""
    if weekday is None or not 0 <= weekday < len(WEEKDAY_LABELS):
        return ""
    return WEEKDAY_LABELS[weekday].lower()


def reason_label(mark) -> str:
    """Подпись причины: «Отпуск», «Больничный», «Выходной»."""
    return REASON_LABELS.get(mark.reason, mark.reason)


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        unavailability_reason_label=reason_label,
        unavailability_span=format_span,
        unavailability_weekday_label=weekday_label,
    )
