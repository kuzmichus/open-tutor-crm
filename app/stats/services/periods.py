"""Разбор периода вкладки «Новые и пробные».

Границы считаются настенным временем педагога через `local_day_bounds`
(design D3 спеки tutor-timezone): «сегодня» ночного занятия при UTC-хранилище
не уезжает в соседний день. Произвольный период — включительный диапазон дат:
конец — начало суток после `date_to`. Мусор в query — не 500, а «Всё время»
(design D6): период передаётся ссылками, опечатка не повод ломать страницу.
"""

from datetime import date, datetime, timedelta

from app.common.services.tutor_time import local_day_bounds, today_local

# Ключи пресетов; «custom» выбирается формой с датами.
PERIOD_OPTIONS = ("all", "today", "7d", "30d", "custom")

# Подписи пресетов для чипов.
PERIOD_LABELS = {
    "all": "Всё время",
    "today": "Сегодня",
    "7d": "7 дней",
    "30d": "30 дней",
}


def _parse_date(raw: str | None) -> date | None:
    """`YYYY-MM-DD` из input[type=date]; пустое или мусорное — `None`."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_period(params, tutor) -> dict:
    """Окно периода как aware-UTC-границы `[start, end)`; без границ — всё время.

    `date_from`/`date_to` — включительно, поэтому `end` — начало суток после
    `date_to`. Незавершённый диапазон (только одна дата) трактуется как всё
    время: половина диапазона — скорее незаполненная форма, чем намерение.
    """
    key = params.get("period", "all")
    if key not in PERIOD_OPTIONS:
        key = "all"

    start: datetime | None = None
    end: datetime | None = None
    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))

    today = today_local(tutor)
    if key == "today":
        start, end = local_day_bounds(today, tutor)
    elif key in ("7d", "30d"):
        days = 7 if key == "7d" else 30
        start, _ = local_day_bounds(today - timedelta(days=days - 1), tutor)
        end, _ = local_day_bounds(today + timedelta(days=1), tutor)
    elif key == "custom" and date_from is not None and date_to is not None:
        if date_from <= date_to:
            start, _ = local_day_bounds(date_from, tutor)
            end, _ = local_day_bounds(date_to + timedelta(days=1), tutor)

    return {
        "key": key,
        "start": start,
        "end": end,
        "date_from": date_from,
        "date_to": date_to,
        # Значения для input[type=date]: ISO-строки или пустые (шаблон не
        # форматирует даты сам — спека «шаблон не считает бизнес-данные»).
        "date_from_input": f"{date_from:%Y-%m-%d}" if date_from else "",
        "date_to_input": f"{date_to:%Y-%m-%d}" if date_to else "",
    }
