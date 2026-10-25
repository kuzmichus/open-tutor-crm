"""Периоды страницы финансов: разбор query-параметра в окно UTC.

Сводка страницы — поток денег за окно `[start, end)` по `occurred_at`.
Границы считаются настенным временем педагога через `local_day_bounds`
(design D2 change'а finance-page): «месяц» при UTC-хранилище не должен
уезжать в соседний календарный месяц из-за сдвига зоны.

Набор периодов продиктован референсом: текущий месяц (по умолчанию),
прошлый месяц, последние три месяца и всё время. Мусор в query — не 500,
а «Этот месяц»: период передаётся селектором, опечатка не повод ломать
страницу (тот же принцип, что у `stats/services/periods.py`).

Сервис не знает про FastAPI: на вход — отображение query-параметров
и карточка репетитора, на выход — словарь для шаблона.
"""

from datetime import date, datetime, timedelta

from app.common.services.tutor_time import local_day_bounds, today_local

# Ключи периодов; «month» — умолчание страницы.
PERIOD_OPTIONS = ("month", "prev", "3m", "all")

# Подписи селектора периода; порядок — порядок <option>.
PERIOD_LABELS = {
    "month": "Этот месяц",
    "prev": "Прошлый месяц",
    "3m": "Последние 3 месяца",
    "all": "Всё время",
}

# Названия месяцев в именительном падеже для подписи «Октябрь 2026».
# Вторая копия в проекте (первая — `tutor/services/presentation`, там
# винительный для «За октябрь»): цена разделения модулей.
_MONTHS = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)


def _month_caption(day: date) -> str:
    """«Октябрь 2026» — месяц и год заглавными."""
    return f"{_MONTHS[day.month - 1]} {day.year}"


def _month_bounds(day: date, tutor) -> tuple[datetime, datetime]:
    """Окно календарного месяца, в который попадает `day` (в зоне педагога)."""
    first = day.replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    start, _ = local_day_bounds(first, tutor)
    end, _ = local_day_bounds(next_month, tutor)
    return start, end


def parse_finance_period(params, tutor) -> dict:
    """Период сводки как aware-UTC-окно `[start, end)`; «всё время» — без границ.

    Возвращает ключ (для селектора), подпись для шапки, границы и признак
    фильтрации: `start is None` — окно не задано, фильтр по дате не нужен.
    """
    key = params.get("period", "month")
    if key not in PERIOD_OPTIONS:
        key = "month"

    today = today_local(tutor)
    start: datetime | None = None
    end: datetime | None = None
    caption: str

    if key == "prev":
        prev_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        start, end = _month_bounds(prev_month, tutor)
        caption = _month_caption(prev_month)
    elif key == "3m":
        first = (today.replace(day=1) - timedelta(days=32)).replace(day=1)
        start = local_day_bounds(first, tutor)[0]
        _, end = _month_bounds(today, tutor)
        caption = f"{_month_caption(first)} — {_month_caption(today)}"
    elif key == "all":
        caption = PERIOD_LABELS["all"]
    else:
        start, end = _month_bounds(today, tutor)
        caption = _month_caption(today)

    return {
        "key": key,
        "caption": caption,
        "start": start,
        "end": end,
    }
