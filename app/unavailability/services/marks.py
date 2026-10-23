"""Отметки недоступности недели: выборка и покрытие дат (design.md D3).

Один `SELECT` с `OR` двух форм — иначе на каждую из семи дат пришлось бы
отдельное обращение (N+1). Покрытие разворачивается в Python по семи датам:
развернуть `weekday`-отметку в конкретные даты проще, чем писать `BETWEEN`
на каждый день недели.

Приоритет (design.md D4): когда на день приходится и отметка периода, и
постоянный выходной, в шапке показывается причина периода — она временная
и конкретная («болею»), а выходной лишь фон. Причины выходного уходят в
`extra_reasons` для всплывающей подсказки.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.unavailability.models.unavailability import (
    REASON_LABELS,
    TutorUnavailability,
)

WEEK_LENGTH = 7


@dataclass(frozen=True)
class DayMark:
    """Недоступность одного дня: главная причина и остальные для подсказки.

    `reason` — машинное значение (`vacation`/`sick`/…), `reason_label` —
    подпись для шапки дня, `extra_reasons` — подписи остальных отметок
    этого дня (идут в `title`, в шапке их не видно).
    """

    reason: str
    reason_label: str
    extra_reasons: tuple[str, ...] = ()


def week_days(monday: date) -> tuple[date, ...]:
    """Семь дат недели, начиная с понедельника."""
    return tuple(monday + timedelta(days=offset) for offset in range(WEEK_LENGTH))


def list_marks(db: Session, tutor_id: str) -> list[TutorUnavailability]:
    """Все отметки этого репетитора.

    Порядок — по дате создания: окончательный порядок списка «Уже отмечено»
    (активные сверху, прошедшие под свёрткой) задаёт `mark_rows`.
    """
    return list(
        db.scalars(
            select(TutorUnavailability)
            .where(TutorUnavailability.tutor_id == tutor_id)
            .order_by(TutorUnavailability.created_at, TutorUnavailability.id)
        )
    )


def marks_for_week(
    db: Session, tutor_id: str, monday: date
) -> list[TutorUnavailability]:
    """Сырые отметки, попадающие хотя бы одним днём в неделю `monday`.

    Период пересекает неделю, если начался не позже её воскресенья и
    (бессрочен или) кончился не раньше понедельника. Постоянный выходной
    попадает в неделю, если его день недели в ней есть и срок не истёк
    до понедельника.
    """
    sunday = monday + timedelta(days=WEEK_LENGTH - 1)
    weekday_numbers = tuple(day.weekday() for day in week_days(monday))

    stmt = (
        select(TutorUnavailability)
        .where(
            TutorUnavailability.tutor_id == tutor_id,
            or_(
                and_(
                    TutorUnavailability.mode == "period",
                    TutorUnavailability.start_date <= sunday,
                    or_(
                        TutorUnavailability.end_date.is_(None),
                        TutorUnavailability.end_date >= monday,
                    ),
                ),
                and_(
                    TutorUnavailability.mode == "weekday",
                    TutorUnavailability.weekday.in_(weekday_numbers),
                    or_(
                        TutorUnavailability.until_date.is_(None),
                        TutorUnavailability.until_date >= monday,
                    ),
                ),
            ),
        )
        .order_by(TutorUnavailability.created_at, TutorUnavailability.id)
    )
    return list(db.scalars(stmt))


def day_reasons(marks: list[TutorUnavailability], day: date) -> list[str]:
    """Причины, покрывающие день: сначала отметки периода, затем выходные.

    Отметка периода важнее постоянного выходного (design.md D4), поэтому
    порядок причин — это и есть приоритет: первая причина главная.
    """
    period_reasons = [
        mark.reason
        for mark in marks
        if mark.mode == "period"
        and mark.start_date is not None
        and mark.start_date <= day
        and (mark.end_date is None or mark.end_date >= day)
    ]
    weekday_reasons = [
        mark.reason
        for mark in marks
        if mark.mode == "weekday"
        and mark.weekday == day.weekday()
        and (mark.until_date is None or mark.until_date >= day)
    ]
    return period_reasons + weekday_reasons


def coverage_for_week(
    db: Session, tutor_id: str, monday: date
) -> dict[date, DayMark]:
    """Дни недели, попадающие в отметки: дата → `DayMark`.

    Дни без отметок в словарь не попадают: шаблон проверяет наличие ключа.
    """
    marks = marks_for_week(db, tutor_id, monday)

    coverage: dict[date, DayMark] = {}
    for day in week_days(monday):
        reasons = day_reasons(marks, day)
        if not reasons:
            continue
        primary = reasons[0]
        primary_label = REASON_LABELS.get(primary, primary)
        extras: list[str] = []
        for reason in reasons[1:]:
            label = REASON_LABELS.get(reason, reason)
            if label != primary_label and label not in extras:
                extras.append(label)
        coverage[day] = DayMark(
            reason=primary,
            reason_label=primary_label,
            extra_reasons=tuple(extras),
        )
    return coverage
