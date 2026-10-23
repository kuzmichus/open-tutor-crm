"""Проверка пересечения урока с отметками недоступности (design.md D5, D6).

Сервис мостик между модулями: даты занятий считает `lesson` (серия — только
Python, `series_generator`), а покрытие отметок — `unavailability`. Живёт в
`lesson`, потому что зависимость односторонняя: `lesson` зависит от
`unavailability`, но не наоборот (design.md D2).

Правило D5: сервер проверяет всегда, даже при `ack_unavailable=1`. Флаг
означает «пользователь видел предупреждение», а не «можно не проверять» —
иначе устаревший `ack` молча создал бы урок.
"""

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.common.services.tutor_time import to_local
from app.lesson.services.series_generator import generate_occurrences
from app.unavailability.services.warning import unavailability_warning

# Подпись причины и число затронутых занятий — ровно то, что показывает
# баннер (design.md D6: число в баннере = числу создаваемых занятий).
Warning = tuple[str, int]


def occurrences_for_form(data: dict, tutor) -> list[datetime] | None:
    """Даты начала занятий формы: одна дата или все даты серии.

    `starts_at` в `data` — aware UTC (разбор формы, design D6), поэтому
    значения переводятся в зону педагога: отметки недоступности — чистые
    календарные даты и сравниваются с локальными днями. Генератор серии
    работает в настенном времени (design D5), ему передаётся наивное
    локальное значение.

    `None` — дат ещё нет (не заполнено «Начало», серия без слотов или без
    даты окончания): проверять нечего, обычная валидация сообщит об этом
    отдельно.
    """
    starts_at: datetime | None = data.get("starts_at")
    if starts_at is None:
        return None

    local_start = to_local(starts_at, tutor)
    if not data.get("repeat"):
        return [local_start]

    slots = data.get("slots")
    until_date: date | None = data.get("until_date")
    if not slots or until_date is None:
        return None
    try:
        return generate_occurrences(
            starts_at=local_start.replace(tzinfo=None),
            slots=slots,
            interval_weeks=data.get("interval_weeks") or 1,
            until_date=until_date,
        )
    except ValueError:
        # Кривые слоты/интервал — ошибка валидации формы, не предупреждение.
        return None


def lesson_unavailability_warning(
    db: Session, tutor_id: str, data: dict, tutor
) -> Warning | None:
    """Предупреждение для формы урока: `(причина, число)` или `None`.

    Для серии считаются все её даты: одно предупреждение на всю серию с
    числом занятий, попадающих в отмеченные дни (design.md D6).
    """
    occurrences = occurrences_for_form(data, tutor)
    if not occurrences:
        return None
    return unavailability_warning(db, tutor_id, occurrences)


def start_unavailability_warning(
    db: Session, tutor_id: str, starts_at: datetime | None, tutor
) -> Warning | None:
    """Предупреждение для одного начала (правка даты, перенос перетаскиванием).

    `starts_at` — aware UTC; день недоступности — локальная дата в зоне
    педагога, поэтому перевод выполняется до проверки.
    """
    if starts_at is None:
        return None
    return unavailability_warning(db, tutor_id, [to_local(starts_at, tutor)])


def warning_context(warning: Warning | None) -> dict:
    """Данные баннера для шаблона: причина, число и текст (design.md D5)."""
    if warning is None:
        return {}
    reason, count = warning
    if count > 1:
        message = (
            f"Дни отмечены как недоступные: {reason}. "
            f"Затронуто занятий: {count}. Всё равно поставить уроки?"
        )
    else:
        message = (
            f"День отмечен как недоступный: {reason}. "
            "Всё равно поставить урок?"
        )
    return {"reason": reason, "count": count, "message": message}
