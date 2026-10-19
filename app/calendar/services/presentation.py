"""Отображение календаря: подписи недели и раскладка блоков по времени.

Чистые функции без БД и HTTP (как demo_schedule): принимают дни недели и
«сейчас», возвращают словари для шаблона. Позиция и высота блока считаются
в часах от 6:00 — шаблон умножает их на CSS-переменную `--cal-hour-h`,
поэтому сетка масштабируется без пересчёта на сервере (design.md D1).
"""

from datetime import date, datetime, timedelta

from app.calendar.services.demo_schedule import demo_students, lessons_word
from app.calendar.services.schedule_day import ScheduleDay
from app.calendar.services.schedule_event import VACATION, ScheduleEvent

# Границы таймлайна: часовые интервалы 6:00–23:00 (спека «Сетка времени»).
GRID_START_HOUR = 6
GRID_END_HOUR = 23
# Часовые строки таймлайна: 6:00 … 22:00, плюс подписи 6:30 … 22:30.
HOURS = tuple(range(GRID_START_HOUR, GRID_END_HOUR))

# Родительный падеж для заголовка диапазона: «12 октября – 18 октября 2026».
MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
# Именительный падеж для угла сетки: «Октябрь 2026».
MONTHS_NOMINATIVE = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)
# Короткие имена дней недели: пн–вс.
WEEKDAY_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def format_range_title(monday: date, sunday: date) -> str:
    """Заголовок панели: «12 октября – 18 октября 2026»."""
    return (
        f"{monday.day} {MONTHS_GENITIVE[monday.month - 1]} – "
        f"{sunday.day} {MONTHS_GENITIVE[sunday.month - 1]} {sunday.year}"
    )


def format_months_label(monday: date, sunday: date) -> str:
    """Подпись месяца/года в левом верхнем углу сетки."""
    first = f"{MONTHS_NOMINATIVE[monday.month - 1]} {monday.year}"
    if monday.month == sunday.month:
        return first
    return f"{first} – {MONTHS_NOMINATIVE[sunday.month - 1]} {sunday.year}"


def format_clock(value) -> str:
    """«14:00» — время без секунд."""
    return f"{value.hour:02d}:{value.minute:02d}"


def format_price(price: int) -> str:
    """«1 200 ₽» — разделитель разрядов неразрывным пробелом."""
    return f"{price:,}".replace(",", "\u00a0") + "\u00a0₽"


def format_time_range(start, end) -> str:
    """«14:00 – 14:40» — интервал времени урока."""
    return f"{format_clock(start)} – {format_clock(end)}"


def build_event_view(event: ScheduleEvent, *, column: int = 1, columns: int = 1, now: datetime) -> dict:
    """Словарь одного блока события для шаблона.

    `column`/`columns` — наложение пересекающихся уроков: каждый получает
    свою долю ширины (спека «Пересекающиеся занятия накладываются»).
    """
    start_minutes = event.start.hour * 60 + event.start.minute
    end_minutes = event.end.hour * 60 + event.end.minute
    top_h = max(0, start_minutes - GRID_START_HOUR * 60) / 60
    height_h = max(15, end_minutes - start_minutes) / 60
    return {
        "is_vacation": event.kind == VACATION,
        "top_h": _num(top_h),
        "height_h": _num(height_h),
        "left_pct": f"{_num((column - 1) * 100 / columns)}%",
        "width_pct": f"{_num(100 / columns)}%",
        "time_label": format_time_range(event.start, event.end),
        "title": f"{event.student} · {format_price(event.price)}",
        "color": event.color,
        "is_group": event.is_group,
        # Прошедшее занятие приглушается: сниженная непрозрачность + пунктир.
        "is_past": _as_datetime(event, event.start) < now,
        # Данные для клиентского drag (спека «Перетаскивание занятия»):
        # дата колонки, начало и длительность в минутах.
        "date": event.day.isoformat(),
        "start_min": start_minutes,
        "duration_min": max(15, end_minutes - start_minutes),
    }


def build_day_view(day: ScheduleDay, *, now: datetime) -> dict:
    """Словарь одного столбца сетки: шапка дня и его события."""
    lessons = layout_events(day.lessons, now=now)
    return {
        "date": day.date,
        "iso_date": day.date.isoformat(),
        "weekday_short": WEEKDAY_SHORT[day.date.weekday()],
        "day_number": day.date.day,
        "is_weekend": day.is_weekend,
        "is_today": day.date == now.date(),
        "dots": [event.color for event in day.lessons],
        "lessons_label": lessons_word(len(day.lessons)) if day.lessons else "",
        "lessons": lessons,
        "has_vacation": any(event.kind == VACATION for event in day.events),
    }


def build_calendar_context(
    days: list[ScheduleDay], *, now: datetime, tutor=None
) -> dict:
    """Полный контекст шаблона календаря по семи дням недели."""
    monday, sunday = days[0].date, days[-1].date
    views = [build_day_view(day, now=now) for day in days]
    return {
        "tutor": tutor,
        "days": views,
        "hours": HOURS,
        "range_title": format_range_title(monday, sunday),
        "months_label": format_months_label(monday, sunday),
        "prev_start": (monday - timedelta(days=7)).isoformat(),
        "next_start": (monday + timedelta(days=7)).isoformat(),
        # Демо-ученики: список выбора в модалке «Новый урок» и данные
        # рендерера карточки (спека «Клик по четверти»).
        "demo_students": demo_students(),
        # Пустая неделя: ни уроков, ни отпуска (спека «Пустая неделя»).
        "is_empty": not any(day.events for day in days),
    }


def layout_events(events: tuple[ScheduleEvent, ...], *, now: datetime) -> list[dict]:
    """Блоки дня с колонками наложения для пересекающихся уроков.

    Пересечения группируются по цепочке: уроки, накладывающиеся друг на
    друга, делят ширину столбца поровну; одиночные занимают всю ширину.
    """
    ordered = sorted(events, key=lambda event: (event.start, event.end))
    views: list[dict] = []
    cluster: list[ScheduleEvent] = []
    cluster_end: int | None = None

    def flush() -> None:
        total = len(cluster)
        for index, event in enumerate(cluster, start=1):
            views.append(
                build_event_view(event, column=index, columns=total, now=now)
            )

    for event in ordered:
        starts = event.start.hour * 60 + event.start.minute
        if cluster and cluster_end is not None and starts >= cluster_end:
            flush()
            cluster, cluster_end = [], None
        cluster.append(event)
        end = event.end.hour * 60 + event.end.minute
        cluster_end = end if cluster_end is None else max(cluster_end, end)
    if cluster:
        flush()
    return views


def _num(value: float) -> str:
    """Число для инлайн-стиля без хвостовых нулей: 8 → «8», 0.667 → «0.667»."""
    return f"{round(value, 4):g}"


def _as_datetime(event: ScheduleEvent, value) -> datetime:
    """Дата события со временем — для сравнения с «сейчас»."""
    return datetime.combine(event.day, value)
