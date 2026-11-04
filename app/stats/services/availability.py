"""Доступные часы: сколько репетитор физически может работать за период.

Источник — настройки профиля: «Рабочее время» задаёт границы рабочего дня
(`workday_start`/`workday_end`), таблица недоступности вычитает отпуска,
больничные и постоянные выходные. Почасовой шаблон недели (разные часы по
дням) в проекте пока не хранится — это осознанно отложено, поэтому
доступные часы считаются «рабочий день × число дней периода».

Отметки читаются одним `SELECT` (`list_marks`) и раскладываются по датам в
Python (`day_reasons`): запрос на каждый день периода был бы N+1, а период
может быть длиной в месяцы.

Битые границы рабочего дня (например, `start >= end` после ручной правки
БД) дают ноль доступных часов, а не отрицательные: страница не должна
показывать минус и не должна падать.
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.calendar.services.presentation import clock_to_minutes
from app.common.services.tutor_time import to_local, today_local
from app.tutor.services.clock import as_utc
from app.tutor.services.settings import get_settings
from app.unavailability.services.marks import day_reasons, list_marks


def workday_minutes(settings) -> int:
    """Длительность рабочего дня в минутах из настроек; битые границы — 0."""
    start = clock_to_minutes(settings.workday_start)
    end = clock_to_minutes(settings.workday_end)
    if end <= start:
        return 0
    return end - start


def period_days(
    tutor,
    *,
    start: datetime | None,
    end: datetime | None,
) -> list[date]:
    """Локальные даты периода `[start, end)` в зоне педагога.

    Без начала отсчёт идёт от даты создания карточки репетитора — раньше
    он работать не мог; без конца — до сегодняшнего дня. Даты перебираются
    по одной, потому что доступность считается посуточно: неделя с
    переводом часов короче/длиннее на час, и деление интервала на сутки
    дало бы сдвиг.
    """
    today = today_local(tutor)
    if start is not None:
        first = to_local(start, tutor).date()
    else:
        created = getattr(tutor, "created_at", None)
        first = to_local(as_utc(created), tutor).date() if created else today
    if end is not None:
        # `end` — начало суток после последнего дня периода: секунда назад
        # даёт именно последний день, а не следующий.
        last = to_local(end - timedelta(seconds=1), tutor).date()
    else:
        last = today
    if last < first:
        return []
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def available_minutes(
    db: Session,
    tutor,
    *,
    start: datetime | None,
    end: datetime | None,
) -> int:
    """Доступные минуты периода: рабочие дни за вычетом отметок недоступности."""
    days = period_days(tutor, start=start, end=end)
    per_day = workday_minutes(get_settings(db, tutor.id))
    if not days or per_day <= 0:
        return 0
    marks = list_marks(db, tutor.id)
    return sum(per_day for day in days if not day_reasons(marks, day))
