"""Детерминированный демо-генератор недельного расписания.

Модели занятий нет, поэтому календарь наполняется чистыми функциями:
неделя → события (уроки и заглушка отпуска) без БД и без участия
пользователя. Паттерн задан по дням недели — день недели + время дают
одно и то же занятие на любой неделе, листание не меняет расписание
(см. design.md D2 и спеку «Демо-занятия детерминированы и повторяются»).

Демо-периоды, в которые занятий нет:

- август — отпуск: каждый день недели помечен заглушкой «Отпуск»;
- новогодний перерыв (30 декабря – 7 января) — неделя без событий,
  «пустое состояние» из спеки.
"""

from datetime import date, datetime, time, timedelta

from app.calendar.services.schedule_day import ScheduleDay
from app.calendar.services.schedule_event import LESSON, VACATION, ScheduleEvent

# Паттерн будней: weekday (0 = пн) → слоты дня в виде кортежей
# (начало, длительность в минутах, ученик, цена, цвет, группа).
# Суббота и воскресенье — выходные, занятий нет.
_LESSONS_BY_WEEKDAY: dict[int, tuple[tuple[time, int, str, int, str, bool], ...]] = {
    0: (
        (time(10, 0), 40, "Иван И.", 1200, "#3b82f6", False),
        (time(17, 0), 50, "Мария С.", 1500, "#8b5cf6", False),
    ),
    1: (
        (time(15, 0), 40, "Елена К.", 1300, "#f97316", False),
        (time(16, 0), 60, "Группа 8Б", 900, "#10b981", True),
    ),
    2: (
        # Пересекающиеся уроки (14:00–14:40 и 14:20–15:00) — пример
        # для проверки наложения блоков в сетке (см. спеку о пересечениях).
        (time(14, 0), 40, "Иван И.", 1200, "#3b82f6", False),
        (time(14, 20), 40, "Ольга Р.", 1400, "#ef4444", False),
        (time(18, 0), 40, "Мария С.", 1500, "#8b5cf6", False),
    ),
    3: (
        (time(11, 0), 60, "Дмитрий С.", 1800, "#0ea5e9", False),
    ),
    4: (
        (time(16, 30), 40, "Елена К.", 1300, "#f97316", False),
        (time(18, 0), 50, "Группа 8Б", 900, "#10b981", True),
    ),
}

# Границы новогоднего перерыва (месяц, день): занятий нет, отпуска нет.
_BREAK_START = (12, 30)
_BREAK_END = (1, 7)


def week_start(value: date | str) -> date:
    """Понедельник недели, содержащей `value` (строка — дата в формате ISO).

    Некорректная строка — ValueError: вызывающая сторона (вьюха) сама
    решает, чем заменить кривой `?start=` (обычно — текущей неделей).
    """
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value - timedelta(days=value.weekday())


def is_vacation_week(monday: date) -> bool:
    """Демо-отпуск: любая неделя августа."""
    return monday.month == 8


def is_between_terms(monday: date) -> bool:
    """Новогодний перерыв: неделя пересекается с 30 декабря – 7 января."""
    sunday = monday + timedelta(days=6)
    for day in (monday, sunday):
        if (day.month, day.day) >= _BREAK_START or (day.month, day.day) <= _BREAK_END:
            return True
    return False


def build_week(value: date | str) -> list[ScheduleDay]:
    """Семь дней недели с демо-событиями.

    `value` нормализуется к понедельнику (в т.ч. строка `?start=`);
    один и тот же вызов всегда возвращает одинаковые данные.
    """
    monday = week_start(value)
    vacation = is_vacation_week(monday)
    gap = is_between_terms(monday)
    return [
        ScheduleDay(
            date=monday + timedelta(days=offset),
            is_weekend=offset >= 5,
            events=_day_events(monday + timedelta(days=offset), vacation=vacation, gap=gap),
        )
        for offset in range(7)
    ]


def lessons_word(count: int) -> str:
    """Число занятий со склонением: «1 урок», «2 урока», «5 уроков»."""
    last_two = abs(count) % 100
    last = abs(count) % 10
    if 11 <= last_two <= 14:
        return f"{count} уроков"
    if last == 1:
        return f"{count} урок"
    if 2 <= last <= 4:
        return f"{count} урока"
    return f"{count} уроков"


def demo_students() -> tuple[dict, ...]:
    """Демо-ученики для формы создания (спека «Клик по четверти»).

    Список собирается из паттерна расписания без дублей и в порядке
    появления: имя, цена, цвет акцента и пометка группового занятия —
    ровно те данные, которыми заполняется карточка нового урока.
    """
    students: dict[str, dict] = {}
    for slots in _LESSONS_BY_WEEKDAY.values():
        for _, _, name, price, color, is_group in slots:
            students.setdefault(
                name,
                {"name": name, "price": price, "color": color, "is_group": is_group},
            )
    return tuple(students.values())


def _day_events(day: date, *, vacation: bool, gap: bool) -> tuple[ScheduleEvent, ...]:
    """События одного дня по демо-правилам недели."""
    if gap:
        # Пустая неделя: ни занятий, ни отпуска.
        return ()
    if vacation:
        # Заглушка «Отпуск» занимает весь день.
        return (
            ScheduleEvent(day=day, start=time(0, 0), end=time(23, 59), kind=VACATION),
        )
    events = []
    for start, minutes, student, price, color, is_group in _LESSONS_BY_WEEKDAY.get(
        day.weekday(), ()
    ):
        end = (datetime.combine(day, start) + timedelta(minutes=minutes)).time()
        events.append(
            ScheduleEvent(
                day=day,
                start=start,
                end=end,
                kind=LESSON,
                student=student,
                price=price,
                color=color,
                is_group=is_group,
            )
        )
    return tuple(events)
