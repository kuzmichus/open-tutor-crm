"""Пачка окон: один расчёт, два входа (design.md D6).

`plan()` считает, что будет создано и что пропущено; `apply()` вызывает
`plan()` и пишет ровно его результат. Предпросмотр физически не может
разойтись с созданием, потому что это один и тот же код.

Генерация идёт в **настенном** времени педагога и только потом каждое окно
переводится в UTC: шаг «длительность + перерыв» через переход на летнее
время не «съезжает» (тот же принцип, что в `series_generator`).

Пачка **частичная**, в отличие от атомарной серии уроков: конфликтующие
окна пропускаются с причиной, остальные создаются. Это осознанное
расхождение (design.md Risks) — одна опечатка не должна отменять пачку.

Причины пропуска: `busy_lesson`, `busy_slot`, `unavailable_day`, `past`.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_day_bounds, to_local, to_utc
from app.slot.models.slot import Slot
from app.slot.services.busy import (
    lesson_spans,
    lessons_for_range,
    overlaps,
    slot_spans,
)
from app.slot.services.slot_form import MAX_SLOT_BATCH, BatchParams
from app.slot.services.slots import slots_between
from app.unavailability.services.marks import coverage_for_week

# Машинные значения причин пропуска; подписи — в `presentation.py`.
SKIP_BUSY_LESSON = "busy_lesson"
SKIP_BUSY_SLOT = "busy_slot"
SKIP_UNAVAILABLE_DAY = "unavailable_day"
SKIP_PAST = "past"

SKIP_REASONS = (
    SKIP_BUSY_LESSON,
    SKIP_BUSY_SLOT,
    SKIP_UNAVAILABLE_DAY,
    SKIP_PAST,
)


@dataclass(frozen=True)
class SlotSkip:
    """Пропущенное окно: когда оно было бы и почему не создано.

    `starts_at` — aware UTC (для сравнения), `day`/`start` — настенные
    значения педагога для отчёта в шаблоне.
    """

    starts_at: datetime
    day: date
    start: time
    reason: str


@dataclass(frozen=True)
class BatchPlan:
    """Результат расчёта пачки: что создать, что пропустить, ошибки формы.

    `create` — aware UTC начала окон. `errors` непустой означает, что
    создавать нельзя ничего (лимит `MAX_SLOT_BATCH`).
    """

    create: tuple[datetime, ...] = ()
    skip: tuple[SlotSkip, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        """Сколько окон предполагалось создать (создаваемые + пропуски)."""
        return len(self.create) + len(self.skip)


def _day_times(params: BatchParams) -> list[time]:
    """Времена окон одного дня: шаг «длительность + перерыв» до конца интервала.

    Последнее окно обязано закончиться не позже `day_end` (спека
    slot-management, «Окно не выходит за конец интервала»).
    """
    duration = timedelta(minutes=params.duration_min)
    step = duration + timedelta(minutes=params.gap_min)
    cursor = datetime.combine(date.min, params.day_start)
    limit = datetime.combine(date.min, params.day_end)
    times: list[time] = []
    while cursor + duration <= limit:
        times.append(cursor.time())
        cursor += step
    return times


def _batch_days(params: BatchParams) -> list[date]:
    """Даты периода, попадающие в выбранные дни недели (включительно)."""
    days: list[date] = []
    cursor = params.date_from
    while cursor <= params.date_to:
        if cursor.weekday() in params.weekdays:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _skip_reason(
    starts_at: datetime,
    finish: datetime,
    *,
    day: date,
    coverage: dict,
    lessons: list[tuple[datetime, datetime]],
    slots: list[tuple[datetime, datetime]],
    now: datetime,
) -> str | None:
    """Причина пропуска окна или None, если его можно создать.

    Порядок проверок задаёт приоритет причины в отчёте: недоступный день
    объясняет пропуск целиком, прошедшее время — тоже, а из двух видов
    занятости урок информативнее точного дубля окна.
    """
    if day in coverage:
        return SKIP_UNAVAILABLE_DAY
    if finish <= now:
        return SKIP_PAST
    if any(overlaps(starts_at, finish, start, end) for start, end in lessons):
        return SKIP_BUSY_LESSON
    if any(overlaps(starts_at, finish, start, end) for start, end in slots):
        return SKIP_BUSY_SLOT
    return None


def plan(
    params: BatchParams,
    *,
    tutor,
    lessons: list[tuple[datetime, datetime]],
    slots: list[tuple[datetime, datetime]],
    coverage: dict,
    now: datetime,
) -> BatchPlan:
    """Рассчитывает пачку: создаваемые окна и пропуски с причинами.

    Чистая функция от уже загруженных данных: ни БД, ни HTTP. Поэтому
    предпросмотр (`GET /tutor/slots/plan`) и создание
    (`POST /tutor/slots/batch`) вызывают её с одинаковыми аргументами и
    получают одинаковый результат.
    """
    created: list[datetime] = []
    skipped: list[SlotSkip] = []

    for day in _batch_days(params):
        for start_time in _day_times(params):
            local_start = datetime.combine(day, start_time)
            starts_at = to_utc(local_start, tutor)
            finish = starts_at + timedelta(minutes=params.duration_min)
            reason = _skip_reason(
                starts_at,
                finish,
                day=day,
                coverage=coverage,
                lessons=lessons,
                slots=slots,
                now=now,
            )
            if reason is None:
                created.append(starts_at)
            else:
                skipped.append(
                    SlotSkip(
                        starts_at=starts_at,
                        day=day,
                        start=start_time,
                        reason=reason,
                    )
                )

    # Лимит проверяется до любых записей: превышение — ошибка формы, а не
    # частично созданная пачка (спека «Лимит окон за одно действие»).
    if len(created) + len(skipped) > MAX_SLOT_BATCH:
        return BatchPlan(
            errors=(
                f"За одно действие можно создать не более {MAX_SLOT_BATCH} окон. "
                "Сократите период или выберите меньше дней.",
            ),
        )

    return BatchPlan(create=tuple(created), skip=tuple(skipped))


def batch_coverage(db: Session, tutor_id: str, date_from: date, date_to: date) -> dict:
    """Покрытие недоступности на весь период пачки.

    `coverage_for_week` считает неделю; период может занимать несколько
    недель, поэтому недельные словари сливаются. Запросов — по одному на
    неделю периода, а не на окно.
    """
    coverage: dict = {}
    monday = date_from - timedelta(days=date_from.weekday())
    last_monday = date_to - timedelta(days=date_to.weekday())
    while monday <= last_monday:
        coverage.update(coverage_for_week(db, tutor_id, monday))
        monday += timedelta(days=7)
    return coverage


def plan_for_tutor(
    db: Session,
    tutor,
    params: BatchParams,
    *,
    now: datetime,
) -> BatchPlan:
    """`plan()` по данным БД: уроки, окна и отметки периода пачки."""
    start, _ = local_day_bounds(params.date_from, tutor)
    _, end = local_day_bounds(params.date_to, tutor)
    lessons = lesson_spans(lessons_for_range(db, tutor.id, start, end))
    slots = slot_spans(slots_between(db, tutor.id, start, end))
    coverage = batch_coverage(db, tutor.id, params.date_from, params.date_to)
    return plan(
        params,
        tutor=tutor,
        lessons=lessons,
        slots=slots,
        coverage=coverage,
        now=now,
    )


def apply(
    db: Session, tutor, params: BatchParams, *, now: datetime
) -> tuple[list[Slot], BatchPlan]:
    """Создаёт окна пачки; возвращает созданные строки и отчёт.

    Пишутся только окна из `plan.create` — частичное создание, не
    атомарное (design.md D6). Гонка с параллельной записью ловится
    уникальностью `(tutor_id, starts_at)`: такая строка становится
    пропуском `busy_slot`, остальные окна сохраняются.
    """
    report = plan_for_tutor(db, tutor, params, now=now)
    if report.errors:
        return [], report

    created: list[Slot] = []
    skipped = list(report.skip)
    for starts_at in report.create:
        slot = Slot(
            tutor_id=tutor.id,
            starts_at=starts_at,
            duration_min=params.duration_min,
            is_public=params.is_public,
        )
        try:
            # Точка сохранения на окно: конфликт одной строки не отменяет
            # остальные (частичное создание пачки).
            with db.begin_nested():
                db.add(slot)
        except IntegrityError:
            local_start = to_local(starts_at, tutor)
            skipped.append(
                SlotSkip(
                    starts_at=starts_at,
                    day=local_start.date(),
                    start=local_start.time(),
                    reason=SKIP_BUSY_SLOT,
                )
            )
            continue
        created.append(slot)

    db.commit()
    return created, BatchPlan(
        create=report.create,
        skip=tuple(sorted(skipped, key=lambda item: item.starts_at)),
        errors=(),
    )
