"""Отображение публичной страницы записи (design.md D5, D6).

Чистые функции без БД и HTTP (паттерн `slot/services/presentation.py`):
на вход — дата или значение из БД и карточка педагога, на выход — строка
для шаблона. Шаблон не форматирует бизнес-данные сам (правило AGENTS.md).

Хелперы не регистрируются в общем Jinja-окружении: их вызывает только
вьюха публичной страницы, собирая контекст (как `build_calendar_context`).
Регистрация сделала бы «дни недели по-русски» доступными всем шаблонам
проекта, где уже есть свои таблицы месяцев.
"""

from datetime import date, datetime, timedelta

from app.common.services.tutor_time import to_local, tutor_zone

# Дни недели от понедельника — порядок `week_days` и сетки.
WEEKDAY_FULL = (
    "Понедельник", "Вторник", "Среда", "Четверг",
    "Пятница", "Суббота", "Воскресенье",
)

# Короткие месяцы в родительном падеже для шапки недели: «26 окт. — 1 нояб.».
# Локальная копия, как в finance/tutor: «умное» переиспользование тянуло бы
# зависимость домена брони на домен календаря ради девяти строк.
MONTHS_SHORT = (
    "янв.", "февр.", "мар.", "апр.", "мая", "июн.",
    "июл.", "авг.", "сент.", "окт.", "нояб.", "дек.",
)

# Полные месяцы в родительном падеже для строки успеха «26 октября 2026».
MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

def weekday_name(day: date) -> str:
    """«Понедельник» — полное имя дня недели."""
    return WEEKDAY_FULL[day.weekday()]

def day_number(day: date) -> str:
    """«26 окт.» — подпись даты в шапке столбца сетки."""
    return f"{day.day} {MONTHS_SHORT[day.month - 1]}"

def week_range(monday: date, sunday: date) -> str:
    """«26 окт. — 1 нояб. 2026» — подпись выбранной недели.

    Год пишется один раз в конце: в макете диапазон читается как одна
    фраза, а не как две даты. Разные годы — оба года явно.
    """
    if monday.year != sunday.year:
        return (
            f"{day_number(monday)} {monday.year} — "
            f"{day_number(sunday)} {sunday.year}"
        )
    return f"{day_number(monday)} — {day_number(sunday)} {sunday.year}"

def utc_offset_label(tutor) -> str:
    """«UTC+4» — текущее смещение зоны педагога от UTC.

    Смещение берётся на момент показа (`utcoffset` текущего момента зоны),
    а не вычисляется из названия: у зон с летним временем оно меняется в
    течение года. Нулевое смещение — «UTC».
    """
    offset = datetime.now(tutor_zone(tutor)).utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset else 0
    if minutes == 0:
        return "UTC"
    sign = "+" if minutes > 0 else "−"
    hours, rest = divmod(abs(minutes), 60)
    if rest:
        return f"UTC{sign}{hours}:{rest:02d}"
    return f"UTC{sign}{hours}"

def zone_banner(zone_name: str, offset_label: str) -> str:
    """Текст баннера о поясе: «Внимание: время указано по … (UTC+4). …».

    Причина в тексте — не украшение: ученик из другого пояса должен понять,
    что 18:30 — это время педагога, а не его собственное (design D6).
    """
    return (
        f"Внимание: время указано по {zone_name} ({offset_label}). "
        "Учитывайте разницу с вашим часовым поясом при записи."
    )

def selected_summary(day: date, start: str, end: str) -> str:
    """«26 октября, понедельник, 18:30 — 19:30» — подпись выбранного окна.

    Форма заявки повторяет выбор словами: ученик мог уйти на другую неделю
    и вернуться, а подсветка в сетке на узком экране не всегда видна.
    """
    return (
        f"{day.day} {MONTHS_GENITIVE[day.month - 1]}, "
        f"{WEEKDAY_FULL[day.weekday()].lower()}, {start} — {end}"
    )

def selected_time_label(starts_at: datetime, duration_min: int, tutor) -> str:
    """«26 октября 2026 18:30 — 19:30» — строка выбранного времени.

    Время считается в зоне педагога, как и вся публичная страница. Конец
    считается от локального начала: длительность — свойство окна, а не
    зоны, поэтому переход на летнее время подпись не сдвигает.
    """
    start = to_local(starts_at, tutor)
    end = start + timedelta(minutes=duration_min or 0)
    return (
        f"{start.day} {MONTHS_GENITIVE[start.month - 1]} {start.year} "
        f"{start.strftime('%H:%M')} — {end.strftime('%H:%M')}"
    )
