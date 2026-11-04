"""Карта загрузки: сетка «день недели × час» текущей недели.

Отвечает на вопрос «где у меня дыры»: каждая ячейка часа — занято, свободно
или недоступно (отпуск, больничный, постоянный выходной). Строки — Пн–Вс,
столбцы — часы рабочего дня из настроек профиля, поэтому карта совпадает с
сеткой календаря.

Состояние ячейки определяется пересечением часового отрезка с интервалами
уроков: урок 10:40–11:20 занимает оба часа — «10:00» и «11:00». Занятие,
начавшееся накануне и перешедшее через полночь, тоже учитывается: границы
прижимаются к суткам, а не отбрасываются.

Инсайт под картой собирается здесь же: шаблон не считает бизнес-данные
(правило модуля), он получает готовое предложение и готовые подписи.
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.calendar.services.presentation import clock_to_minutes, format_minutes
from app.common.services.tutor_time import local_week_bounds, to_local, today_local
from app.stats.services.availability import workday_minutes
from app.stats.services.hours import week_busy_intervals
from app.tutor.services.settings import get_settings
from app.unavailability.models.unavailability import REASON_LABELS, WEEKDAY_LABELS
from app.unavailability.services.marks import day_reasons, list_marks, week_days

# Состояния ячейки: классы `stats-heat__cell--<state>` в styles.css.
CELL_BUSY = "busy"
CELL_FREE = "free"
CELL_UNAVAILABLE = "unavailable"

CELL_LABELS = {
    CELL_BUSY: "занято",
    CELL_FREE: "свободно",
    CELL_UNAVAILABLE: "недоступно",
}

# Полные названия дней для фразы инсайта («Самое большое окно — вторник»).
WEEKDAY_NAMES = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)

MINUTES_PER_DAY = 24 * 60

NO_WORKDAY_INSIGHT = (
    "Рабочее время не задано — укажите его в профиле, чтобы видеть "
    "свободные окна на карте."
)
NO_FREE_INSIGHT = (
    "Свободных окон на этой неделе нет: все рабочие часы заняты или "
    "отмечены как недоступные."
)


def free_hours_phrase(hours: int) -> str:
    """«6 свободных астрономических часов» — со склонением по числу."""
    last_two = abs(hours) % 100
    last = abs(hours) % 10
    if 11 <= last_two <= 14:
        return f"{hours} свободных астрономических часов"
    if last == 1:
        return f"{hours} свободный астрономический час"
    if 2 <= last <= 4:
        return f"{hours} свободных астрономических часа"
    return f"{hours} свободных астрономических часов"


def _day_minutes(starts_at: datetime, duration_min: int, day: date, tutor) -> tuple[int, int]:
    """Отрезок урока в минутах суток `day` с прижиманием к суткам.

    Урок соседних суток даёт отрезок за границей 0..1440 и после прижимания
    либо исчезает, либо оставляет только свою «перешедшую» часть.
    """
    local = to_local(starts_at, tutor)
    start = (local.date() - day).days * MINUTES_PER_DAY
    start += local.hour * 60 + local.minute
    end = start + duration_min
    return max(0, start), min(MINUTES_PER_DAY, end)


def _busy_hours(
    day: date,
    hours: list[int],
    intervals: list[tuple[datetime, int]],
    tutor,
) -> set[int]:
    """Часы суток, пересекающиеся хотя бы с одним уроком."""
    busy: set[int] = set()
    for starts_at, duration_min in intervals:
        start, end = _day_minutes(starts_at, duration_min, day, tutor)
        if end <= start:
            continue
        for hour in hours:
            if start < (hour + 1) * 60 and end > hour * 60:
                busy.add(hour)
    return busy


def _largest_window(
    rows: list[dict], hours: list[int]
) -> tuple[int, int, int, int] | None:
    """Самое длинное непрерывное окно свободных часов: `(день, с, до)`.

    Возвращаются часы суток (начало и конец окна), длина — в часах. При
    равной длине побеждает более ранний день: инсайт должен быть стабильным
    от запроса к запросу.
    """
    best: tuple[int, int, int, int] | None = None
    for index, row in enumerate(rows):
        run_start: int | None = None
        for position, cell in enumerate(row["cells"]):
            if cell["state"] == CELL_FREE and run_start is None:
                run_start = position
            if cell["state"] != CELL_FREE and run_start is not None:
                length = position - run_start
                if best is None or length > best[2]:
                    best = (index, hours[run_start], hours[position], length)
                run_start = None
        if run_start is not None:
            length = len(row["cells"]) - run_start
            if best is None or length > best[2]:
                best = (index, hours[run_start], hours[-1] + 1, length)
    return best


def _insight(rows: list[dict], hours: list[int], total_free: int) -> str:
    """Готовая фраза инсайта под картой."""
    if total_free == 0:
        return NO_FREE_INSIGHT
    window = _largest_window(rows, hours)
    if window is None:
        return NO_FREE_INSIGHT
    day_index, from_hour, to_hour, _length = window
    weekday = WEEKDAY_NAMES[day_index]
    return (
        f"У вас {free_hours_phrase(total_free)} на этой неделе. "
        f"Самое большое окно — {weekday} с {format_minutes(from_hour * 60)} "
        f"до {format_minutes(to_hour * 60)}."
    )


def heatmap_context(db: Session, tutor, *, now: datetime) -> dict:
    """Контекст карты загрузки на текущую календарную неделю.

    `now` — aware-UTC «сейчас» из вьюхи; неделя считается в зоне педагога,
    поэтому ночной запрос не уезжает на прошлую неделю.
    """
    today = today_local(tutor)
    monday = today - timedelta(days=today.weekday())
    settings = get_settings(db, tutor.id)

    if workday_minutes(settings) <= 0:
        return {
            "has_workday": False,
            "hours": [],
            "rows": [],
            "legend": CELL_LABELS,
            "total_free_hours": 0,
            "insight": NO_WORKDAY_INSIGHT,
        }

    start_min = clock_to_minutes(settings.workday_start)
    end_min = clock_to_minutes(settings.workday_end)
    hours = list(range(start_min // 60, (end_min + 59) // 60))

    week_start, week_end = local_week_bounds(monday, tutor)
    intervals = week_busy_intervals(
        db, tutor.id, start=week_start, end=week_end
    )
    marks = list_marks(db, tutor.id)

    rows: list[dict] = []
    total_free = 0
    for day in week_days(monday):
        reasons = day_reasons(marks, day)
        unavailable = bool(reasons)
        busy = set() if unavailable else _busy_hours(day, hours, intervals, tutor)
        cells = []
        for hour in hours:
            if unavailable:
                state = CELL_UNAVAILABLE
                label = REASON_LABELS.get(reasons[0], reasons[0])
            elif hour in busy:
                state = CELL_BUSY
                label = CELL_LABELS[CELL_BUSY]
            else:
                state = CELL_FREE
                label = CELL_LABELS[CELL_FREE]
            if state == CELL_FREE:
                total_free += 1
            cells.append(
                {
                    "hour": hour,
                    "state": state,
                    "label": label,
                    "title": f"{WEEKDAY_LABELS[day.weekday()]}, "
                    f"{format_minutes(hour * 60)} — {label}",
                }
            )
        rows.append(
            {
                "date": day,
                "weekday_short": WEEKDAY_LABELS[day.weekday()],
                "day_number": day.day,
                "is_today": day == today,
                "unavailable": unavailable,
                "unavailable_label": (
                    REASON_LABELS.get(reasons[0], reasons[0]) if reasons else ""
                ),
                "cells": cells,
            }
        )

    return {
        "has_workday": True,
        "hours": [
            {
                "hour": hour,
                "label": format_minutes(hour * 60),
                "short_label": f"{hour:02d}",
            }
            for hour in hours
        ],
        "rows": rows,
        "legend": CELL_LABELS,
        "total_free_hours": total_free,
        "insight": _insight(rows, hours, total_free),
    }
