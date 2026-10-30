"""Отображение календаря: подписи недели и раскладка блоков по времени.

Чистые функции без БД и HTTP: принимают дни недели и
«сейчас», возвращают словари для шаблона. Позиция и высота блока считаются
в часах от начала сетки (рабочее время репетитора) — шаблон умножает их
на CSS-переменную `--cal-hour-h`, поэтому сетка масштабируется без
пересчёта на сервере (design.md D1).
"""

from datetime import date, datetime, timedelta

from app.calendar.services.color_mode import (
    DEFAULT_COLOR_MODE,
    STATUS,
    status_color,
)
from app.calendar.services.schedule_day import ScheduleDay
from app.calendar.services.schedule_event import ScheduleEvent
from app.slot.services.presentation import is_muted as slot_is_muted
from app.slot.services.presentation import state_label as slot_state_label
from app.slot.services.public_link import PUBLIC_PREFIX

# Границы таймлайна по умолчанию, минуты суток 6:00–23:00: дефолт рабочего
# времени репетитора до первого сохранения настройки (tutor_settings.workday_*).
DEFAULT_GRID_START_MIN = 6 * 60
DEFAULT_GRID_END_MIN = 23 * 60

# Четверти часа внутри часовой строки, минуты от её начала.
QUARTER_STEPS = (0, 15, 30, 45)

# Акцент карточки окна: собственный токен дизайн-системы, а не цвет цели.
# Окно — не ученик и не группа, поэтому палитра целей к нему не применима
# (спека calendar, «Карточка окна визуально отличается от урока»). Ссылка
# на переменную, а не литерал: тема задаёт значение сама.
SLOT_ACCENT = "var(--cal-slot-accent)"

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


def format_minutes(minutes: int) -> str:
    """«14:30» — минуты суток строкой «ЧЧ:ММ»."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def clock_to_minutes(clock: str) -> int:
    """Минуты суток из строки «ЧЧ:ММ»; кривое значение — дефолт начала.

    Настройка валидируется формой, но сетка не должна падать на старой
    или испорченной строке: незамеченный мусор даёт дефолтную сетку.
    """
    try:
        hours, minutes = clock.strip().split(":")
        hours, minutes = int(hours), int(minutes)
    except ValueError:
        return DEFAULT_GRID_START_MIN
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return DEFAULT_GRID_START_MIN
    return hours * 60 + minutes


def build_grid_rows(grid_start_min: int, grid_end_min: int) -> list[dict]:
    """Часовые строки таймлайна с готовыми подписями и четвертями.

    Строка существует, пока её начало раньше конца рабочего времени;
    подпись половины («+:30») — только если она не за концом, четверти
    строки — тоже отфильтрованы по `< end`. Шаблон получает готовые
    строки «ЧЧ:ММ» и не делает арифметики над часами сам (дизайн D3).
    """
    rows: list[dict] = []
    for row_start in range(grid_start_min, grid_end_min, 60):
        quarters = [
            {
                "start_label": format_minutes(row_start + step),
                "end_label": format_minutes(row_start + step + 15),
            }
            for step in QUARTER_STEPS
            if row_start + step < grid_end_min
        ]
        rows.append(
            {
                "hour_label": format_minutes(row_start),
                "half_label": (
                    format_minutes(row_start + 30)
                    if row_start + 30 < grid_end_min
                    else ""
                ),
                "quarters": quarters,
            }
        )
    return rows


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


def _visible_span(
    start_minutes: int, end_minutes: int, grid_start_min: int, grid_end_min: int
) -> tuple[int, int]:
    """Видимые границы карточки в минутах суток — с зажимом в сетку.

    Занятие вне рабочего времени не пропадает (спека «Занятия вне рабочего
    времени остаются видимыми»): пересекающее границу зажимается ей,
    целиком лежащее за сеткой — прижимается к соответствующему краю
    своей реальной длительностью, чтобы остаться внутри колонки.
    """
    duration = max(15, end_minutes - start_minutes)
    if end_minutes <= grid_start_min:
        # Урок раньше рабочего времени — прижат к верхней границе.
        return grid_start_min, grid_start_min + duration
    if start_minutes >= grid_end_min:
        # Урок позже рабочего времени — прижат к нижней границе.
        top = max(grid_start_min, grid_end_min - duration)
        return top, grid_end_min
    return (
        max(start_minutes, grid_start_min),
        min(end_minutes, grid_end_min),
    )


def build_event_view(
    event: ScheduleEvent,
    *,
    column: int = 1,
    columns: int = 1,
    now: datetime,
    color_mode: str = DEFAULT_COLOR_MODE,
    grid_start_min: int = DEFAULT_GRID_START_MIN,
    grid_end_min: int = DEFAULT_GRID_END_MIN,
) -> dict:
    """Словарь одного блока события для шаблона — урока или окна.

    `column`/`columns` — наложение пересекающихся событий: каждый получает
    свою долю ширины (спека «Пересекающиеся занятия накладываются»).
    `color_mode` — активный режим раскраски (design.md D5): акцент урока
    считается тем же правилом, что и точки в шапке дня.
    `grid_start_min`/`grid_end_min` — рабочее время репетитора (минуты
    суток): `top_h` считается от начала сетки, а края карточки зажимаются
    её границами (дизайн D3).

    Поля урока и окна различаются (design D5): у окна нет цели, цены и
    статуса урока, зато есть `slot_id`, `slot_state` и подпись состояния.
    Общий словарь с пустыми значениями чужой ветки — чтобы шаблон не падал
    на `undefined` и мог читать любое поле без `is defined`.
    """
    start_minutes = event.start.hour * 60 + event.start.minute
    end_minutes = event.end.hour * 60 + event.end.minute
    top_min, bottom_min = _visible_span(
        start_minutes, end_minutes, grid_start_min, grid_end_min
    )
    top_h = (top_min - grid_start_min) / 60
    height_h = max(15, bottom_min - top_min) / 60

    view = {
        "top_h": _num(top_h),
        "height_h": _num(height_h),
        "left_pct": f"{_num((column - 1) * 100 / columns)}%",
        "width_pct": f"{_num(100 / columns)}%",
        "time_label": format_time_range(event.start, event.end),
        # Данные для клиентского drag (спека «Перетаскивание занятия»):
        # дата колонки, начало и длительность в минутах. Фактические, не
        # зажатые: карточка вне рабочего времени при перетаскивании
        # возвращается в интервал, а подпись времени показывает реальный
        # урок (спека «Данные о времени — фактический интервал»).
        "date": event.day.isoformat(),
        "start_min": start_minutes,
        "duration_min": max(15, end_minutes - start_minutes),
        "kind": event.kind,
        "is_slot": event.is_slot,
    }
    if event.is_slot:
        view.update(_slot_fields(event))
    else:
        view.update(_lesson_fields(event, now=now, color_mode=color_mode))
    return view


def _lesson_fields(
    event: ScheduleEvent, *, now: datetime, color_mode: str
) -> dict:
    """Поля карточки урока: цель, цена, акцент и признаки состояния."""
    overdue = is_overdue(event, now=now)
    price_label = format_price(event.price)
    # Имя цели — обязательная часть карточки; цена дописывается только
    # когда она задана, иначе заголовок кончался бы бесполезным «0 ₽».
    title = f"{event.student} · {price_label}" if price_label else event.student
    return {
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
        # Данные реального урока: непустой id отличает его от окна и
        # служит адресом формы редактирования (design.md D7).
        "lesson_id": event.lesson_id,
        "target_id": event.target_id,
        # Поля окна пусты: шаблон читает их только в ветке `is_slot`.
        "slot_id": "",
        "slot_state": "",
        "state_label": "",
        "is_muted": False,
    }


def _slot_fields(event: ScheduleEvent) -> dict:
    """Поля карточки окна: подпись состояния, приглушение, акцент токена.

    Акцент окна — `--cal-slot-accent`, а не цвет цели и не цвет статуса:
    окно не принадлежит ученику, и в режиме «По статусу» красный
    «просрочен» к нему не применим (design D5). Приглушение считает
    `slot_is_muted` по состоянию — занятые и прошедшие окна гаснут
    (спека calendar, «Занятое окно приглушено»).
    """
    label = slot_state_label(event.slot_state)
    return {
        # Заголовок и подпись цели — состояние окна: имени у окна нет.
        "title": label,
        "target_name": label,
        "price_label": "",
        "color": SLOT_ACCENT,
        "is_group": False,
        "is_past": False,
        "is_overdue": False,
        "is_completed": False,
        "lesson_id": "",
        "target_id": "",
        "slot_id": event.slot_id,
        "slot_state": event.slot_state,
        "state_label": label,
        "is_muted": slot_is_muted(event.slot_state),
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


def build_day_view(
    day: ScheduleDay,
    *,
    now: datetime,
    color_mode: str = DEFAULT_COLOR_MODE,
    grid_start_min: int = DEFAULT_GRID_START_MIN,
    grid_end_min: int = DEFAULT_GRID_END_MIN,
) -> dict:
    """Словарь одного столбца сетки: шапка дня и его события.

    `unavailable` — подпись причины отметки для шапки дня (`""` — день
    доступен), `unavailable_title` — все причины дня для всплывающей
    подсказки (design.md D4: периода важнее выходного).

    Флага «выходной» нет: выходные задаёт только таблица отметок, поэтому
    суббота и воскресенье выглядят как обычные дни, пока репетитор не
    отметил их сам.
    """
    lessons = layout_events(
        day.events,
        now=now,
        color_mode=color_mode,
        grid_start_min=grid_start_min,
        grid_end_min=grid_end_min,
    )
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
    grid_start_min: int = DEFAULT_GRID_START_MIN,
    grid_end_min: int = DEFAULT_GRID_END_MIN,
) -> dict:
    """Полный контекст шаблона календаря по семи дням недели.

    `grid_start_min`/`grid_end_min` — рабочее время репетитора (минуты
    суток): из них строятся часовые строки, конечная метка и `data-`-
    атрибуты границ для клиентского скрипта (дизайн D3, D4).
    """
    monday, sunday = days[0].date, days[-1].date
    views = [
        build_day_view(
            day,
            now=now,
            color_mode=color_mode,
            grid_start_min=grid_start_min,
            grid_end_min=grid_end_min,
        )
        for day in days
    ]
    # Публичная ссылка на эту неделю (design D7): «Ссылка для записи»
    # копирует её, а не адрес календаря. Собирается сервером из `tutor_id` и
    # понедельника — клиент не должен угадывать формат адреса.
    tutor_id = getattr(tutor, "id", "") or ""
    return {
        "tutor": tutor,
        "days": views,
        "grid_rows": build_grid_rows(grid_start_min, grid_end_min),
        "grid_start_min": grid_start_min,
        "grid_end_min": grid_end_min,
        "grid_end_label": format_minutes(grid_end_min),
        "range_title": format_range_title(monday, sunday),
        "months_label": format_months_label(monday, sunday),
        "prev_start": (monday - timedelta(days=7)).isoformat(),
        "next_start": (monday + timedelta(days=7)).isoformat(),
        # Текущая неделя рендера: по ней #calendar-swap перерисовывается
        # после сохранения урока, не теряя открытую неделю (design.md D6).
        "current_start": monday.isoformat(),
        # Публичный адрес недели: префикс и id репетитора — из сервера,
        # понедельник подставляет `calendar.js` из видимой сетки, чтобы
        # листание недель не оставляло в ссылке прошлую.
        "public_prefix": PUBLIC_PREFIX,
        "tutor_id": tutor_id,
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
    grid_start_min: int = DEFAULT_GRID_START_MIN,
    grid_end_min: int = DEFAULT_GRID_END_MIN,
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
                    grid_start_min=grid_start_min,
                    grid_end_min=grid_end_min,
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
