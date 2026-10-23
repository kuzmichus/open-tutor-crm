"""Отображение календаря: подписи недели и раскладка блоков по времени.

Чистые функции без БД и HTTP: принимают дни недели и
«сейчас», возвращают словари для шаблона. Позиция и высота блока считаются
в часах от 6:00 — шаблон умножает их на CSS-переменную `--cal-hour-h`,
поэтому сетка масштабируется без пересчёта на сервере (design.md D1).
"""

from datetime import date, datetime, timedelta

from app.calendar.services.color_mode import (
    DEFAULT_COLOR_MODE,
    STATUS,
    status_color,
)
from app.calendar.services.schedule_day import ScheduleDay
from app.calendar.services.schedule_event import ScheduleEvent

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


def lessons_word(count: int) -> str:
    """Число занятий со склонением: «1 урок», «2 урока», «5 уроков».

    Переехала сюда из удалённого демо-генератора: подпись используется
    живым рендером шапки дня (design.md D7).
    """
    last_two = abs(count) % 100
    last = abs(count) % 10
    if 11 <= last_two <= 14:
        return f"{count} уроков"
    if last == 1:
        return f"{count} урок"
    if 2 <= last <= 4:
        return f"{count} урока"
    return f"{count} уроков"


def format_price(price: int | None) -> str:
    """«1 200 ₽» — разделитель разрядов неразрывным пробелом.

    Пустая или нулевая цена даёт пустую строку: в карточке календаря
    «0 ₽» ничего не сообщает, а место занимает (цена урока не задана).
    """
    if not price:
        return ""
    return f"{price:,}".replace(",", "\u00a0") + "\u00a0₽"


def format_time_range(start, end) -> str:
    """«14:00 – 14:40» — интервал времени урока."""
    return f"{format_clock(start)} – {format_clock(end)}"


def build_event_view(
    event: ScheduleEvent,
    *,
    column: int = 1,
    columns: int = 1,
    now: datetime,
    color_mode: str = DEFAULT_COLOR_MODE,
) -> dict:
    """Словарь одного блока события для шаблона.

    `column`/`columns` — наложение пересекающихся уроков: каждый получает
    свою долю ширины (спека «Пересекающиеся занятия накладываются»).
    `color_mode` — активный режим раскраски (design.md D5): акцент считается
    тем же правилом, что и точки в шапке дня.
    """
    start_minutes = event.start.hour * 60 + event.start.minute
    end_minutes = event.end.hour * 60 + event.end.minute
    top_h = max(0, start_minutes - GRID_START_HOUR * 60) / 60
    height_h = max(15, end_minutes - start_minutes) / 60
    overdue = is_overdue(event, now=now)
    price_label = format_price(event.price)
    # Имя цели — обязательная часть карточки; цена дописывается только
    # когда она задана, иначе заголовок кончался бы бесполезным «0 ₽».
    title = f"{event.student} · {price_label}" if price_label else event.student
    return {
        "top_h": _num(top_h),
        "height_h": _num(height_h),
        "left_pct": f"{_num((column - 1) * 100 / columns)}%",
        "width_pct": f"{_num(100 / columns)}%",
        "time_label": format_time_range(event.start, event.end),
        "title": title,
        "target_name": event.student,
        "price_label": price_label,
        "color": event_accent(event, now=now, color_mode=color_mode),
        "is_group": event.is_group,
        # Прошедшее занятие приглушается: сниженная непрозрачность + пунктир.
        # Сравнение aware UTC с aware UTC (design D4) — «прошло» больше не
        # зависит от того, в каком кадре собраны «сейчас» и время урока.
        "is_past": event.starts_at < now,
        # «Просрочен» — запланированный урок, чьё время уже прошло
        # (design.md D5): отличается от проведённого и от будущего.
        "is_overdue": overdue,
        "is_completed": event.is_completed,
        # Данные реального урока: непустой id отличает его от демо-события
        # и служит адресом формы редактирования (design.md D7).
        "lesson_id": event.lesson_id,
        "target_id": event.target_id,
        # Данные для клиентского drag (спека «Перетаскивание занятия»):
        # дата колонки, начало и длительность в минутах.
        "date": event.day.isoformat(),
        "start_min": start_minutes,
        "duration_min": max(15, end_minutes - start_minutes),
    }


def is_overdue(event: ScheduleEvent, *, now: datetime) -> bool:
    """Запланированный урок, время которого уже прошло (design.md D5).

    Сравниваются aware UTC: `ends_at` события и `now` из контекста
    (design D4), поэтому результат не зависит от зоны машины.
    """
    if event.is_completed:
        return False
    return event.ends_at < now


def event_accent(event: ScheduleEvent, *, now: datetime, color_mode: str) -> str:
    """Акцентный цвет события по активному режиму раскраски (design.md D5).

    Одно правило на карточку и на точку в шапке дня: в режиме «По статусу»
    цвет зависит от `status`/просрочки, в режиме «По цели» — от цвета
    ученика или группы.
    """
    if color_mode == STATUS:
        return status_color(
            is_completed=event.is_completed,
            is_overdue=is_overdue(event, now=now),
        )
    return event.color


def build_day_view(day: ScheduleDay, *, now: datetime, color_mode: str = DEFAULT_COLOR_MODE) -> dict:
    """Словарь одного столбца сетки: шапка дня и его события.

    `unavailable` — подпись причины отметки для шапки дня (`""` — день
    доступен), `unavailable_title` — все причины дня для всплывающей
    подсказки (design.md D4: периода важнее выходного).

    Флага «выходной» нет: выходные задаёт только таблица отметок, поэтому
    суббота и воскресенье выглядят как обычные дни, пока репетитор не
    отметил их сам.
    """
    lessons = layout_events(day.events, now=now, color_mode=color_mode)
    mark = day.unavailable
    return {
        "date": day.date,
        "iso_date": day.date.isoformat(),
        "weekday_short": WEEKDAY_SHORT[day.date.weekday()],
        "day_number": day.date.day,
        "is_today": day.date == now.date(),
        # Точки шапки — тем же правилом, что и акцент карточки: цвета
        # точки и карточки урока не могут разойтись (design.md D5).
        "dots": [
            event_accent(event, now=now, color_mode=color_mode)
            for event in day.events
        ],
        "lessons_label": lessons_word(len(day.events)) if day.events else "",
        "lessons": lessons,
        # Причина отметки в шапке дня. Плашки «Выходной» больше нет, так что
        # отметка ничего не перекрывает — она единственная подпись о
        # нерабочем дне (спека calendar, «Выходные задаёт репетитор»).
        "unavailable": mark.reason_label if mark else "",
        "unavailable_title": (
            ", ".join((mark.reason_label,) + mark.extra_reasons) if mark else ""
        ),
    }


def build_calendar_context(
    days: list[ScheduleDay],
    *,
    now: datetime,
    tutor=None,
    color_mode: str = DEFAULT_COLOR_MODE,
) -> dict:
    """Полный контекст шаблона календаря по семи дням недели."""
    monday, sunday = days[0].date, days[-1].date
    views = [build_day_view(day, now=now, color_mode=color_mode) for day in days]
    return {
        "tutor": tutor,
        "days": views,
        "hours": HOURS,
        "range_title": format_range_title(monday, sunday),
        "months_label": format_months_label(monday, sunday),
        "prev_start": (monday - timedelta(days=7)).isoformat(),
        "next_start": (monday + timedelta(days=7)).isoformat(),
        # Текущая неделя рендера: по ней #calendar-swap перерисовывается
        # после сохранения урока, не теряя открытую неделю (design.md D6).
        "current_start": monday.isoformat(),
        # Активный режим раскраски: контрол панели и `?color=` при листании
        # (design.md D5).
        "color_mode": color_mode,
        "color_target": color_mode != STATUS,
        # Пустая неделя: ни уроков, ни отметок недоступности (спека
        # «Пустая неделя»: пояснение не должно называть неделю свободной,
        # если в ней есть отметка).
        "is_empty": not any(day.events or day.unavailable for day in days),
    }


def layout_events(
    events: tuple[ScheduleEvent, ...],
    *,
    now: datetime,
    color_mode: str = DEFAULT_COLOR_MODE,
) -> list[dict]:
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
                build_event_view(
                    event,
                    column=index,
                    columns=total,
                    now=now,
                    color_mode=color_mode,
                )
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
