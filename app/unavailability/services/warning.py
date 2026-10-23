"""Предупреждение о постановке урока в отмеченный день (design.md D5, D6).

Сервер считает пересечение фактических дат занятий с покрытием отметок:
в форме может быть серия, даты которой знает только Python
(`series_generator.generate_occurrences`), поэтому клиентский `confirm()`
здесь не годится.

Проверка идёт по списку дат, а не по дням календаря: `MAX_SERIES_OCCURRENCES`
ограничивает его 520 значениями, а покрытие собирается по неделям — на
каждую неделю серии один запрос, а не на каждый день (design.md D6).

Сервис не знает про FastAPI: на вход — сессия, `tutor_id` и даты начала
занятий, на выход — `(подпись причины, число затронутых)` или `None`.
"""

from collections.abc import Iterable
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.unavailability.services.marks import coverage_for_week


def _monday(value: date) -> date:
    """Понедельник недели, содержащей дату (как `calendar.week_start`)."""
    return value - timedelta(days=value.weekday())


def unavailability_warning(
    db: Session, tutor_id: str, occurrences: Iterable[datetime | date]
) -> tuple[str, int] | None:
    """Пересечение дат занятий с отметками: `(причина, сколько)` или `None`.

    Число — количество дат, попавших в отмеченные дни: ровно столько
    занятий реально создастся, поэтому баннер не расходится с результатом
    (design.md D6). Причина — подпись отметки первой затронутой даты.
    """
    days: list[date] = []
    for occurrence in occurrences:
        day = occurrence.date() if isinstance(occurrence, datetime) else occurrence
        if day not in days:
            days.append(day)
    if not days:
        return None

    # Покрытие считается один раз на неделю: серия почти всегда укладывается
    # в несколько недель, а запрос на каждый день был бы лишним.
    coverage_by_week: dict[date, dict] = {}
    first_label: str | None = None
    count = 0
    for day in sorted(days):
        monday = _monday(day)
        if monday not in coverage_by_week:
            coverage_by_week[monday] = coverage_for_week(db, tutor_id, monday)
        mark = coverage_by_week[monday].get(day)
        if mark is None:
            continue
        count += 1
        if first_label is None:
            first_label = mark.reason_label

    if first_label is None:
        return None
    return first_label, count
