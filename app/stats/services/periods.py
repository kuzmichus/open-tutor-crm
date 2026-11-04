"""Разбор периода вкладки статистики.

Границы считаются настенным временем педагога через `local_day_bounds`
(design D3 спеки tutor-timezone): «сегодня» ночного занятия при UTC-хранилище
не уезжает в соседний день. Произвольный период — включительный диапазон дат:
конец — начало суток после `date_to`. Мусор в query — не 500, а период по
умолчанию (design D6): период передаётся ссылками, опечатка не повод ломать
страницу.

Умолчание параметра различается по вкладкам: «Новые и пробные» исторически
показывают «Всё время» (`default="all"`), а «Обзор» — последние 30 дней
(`default="30d"`), потому что загрузка и выручка за всё время отвечают не на
тот вопрос, с которым страницу открывают.
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

# Длина пресетов в днях включительно (кроме «сегодня» и «всё время»).
PRESET_DAYS = {"7d": 7, "30d": 30}


def _parse_date(raw: str | None) -> date | None:
    """`YYYY-MM-DD` из input[type=date]; пустое или мусорное — `None`."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _preset_bounds(key: str, tutor) -> tuple[datetime | None, datetime | None]:
    """Границы пресета `[start, end)`; «Всё время» — без границ."""
    today = today_local(tutor)
    if key == "today":
        return local_day_bounds(today, tutor)
    if key in PRESET_DAYS:
        days = PRESET_DAYS[key]
        start, _ = local_day_bounds(today - timedelta(days=days - 1), tutor)
        end, _ = local_day_bounds(today + timedelta(days=1), tutor)
        return start, end
    return None, None


def parse_period(params, tutor, *, default: str = "all") -> dict:
    """Окно периода как aware-UTC-границы `[start, end)`; без границ — всё время.

    `date_from`/`date_to` — включительно, поэтому `end` — начало суток после
    `date_to`. Незавершённый диапазон (только одна дата или мусор) трактуется
    как период по умолчанию: половина диапазона — скорее незаполненная форма,
    чем намерение.
    """
    if default not in PERIOD_OPTIONS:
        default = "all"
    key = params.get("period", default)
    if key not in PERIOD_OPTIONS:
        key = default

    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))

    if key == "custom" and date_from is not None and date_to is not None:
        if date_from <= date_to:
            start, _ = local_day_bounds(date_from, tutor)
            end, _ = local_day_bounds(date_to + timedelta(days=1), tutor)
        else:
            # Диапазон наоборот — тоже незаполненная форма: показываем
            # период по умолчанию, а не пустоту.
            start, end = _preset_bounds(default, tutor)
    else:
        if key == "custom":
            key = default
        start, end = _preset_bounds(key, tutor)

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