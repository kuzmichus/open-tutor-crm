"""Время как деньги: проведённые часы, стоимость часа, простой и типы занятий.

Глоссарий задачи (change finance-hours-idle-revenue) фиксирует разделение,
которого не хватало странице финансов:

- **проведённые часы** — астрономическое время только состоявшихся занятий
  (`Lesson.status='completed'`), включая те, за которые ученик ещё не
  заплатил. Источник — `stats/services/hours.completed_minutes`: правило
  «групповой урок считается один раз» уже живёт там, второй копии здесь нет;
- **средняя стоимость часа (RevPTH)** — `начисленный доход / проведённые
  часы`: сколько денег приносит один астрономический час времени;
- **свободные часы (простой)** — доступные по рабочему шаблону минуты минус
  занятые уроки любого статуса. Запланированный урок тоже занимает окно,
  поэтому «свободным» его называть нельзя (та же логика, что у
  `stats/services/hours.week_busy_intervals`);
- **упущенная выручка** — денежный эквивалент свободных часов:
  `свободные часы × RevPTH`.

Окно простоя — «текущий/будущий месяц» из ТЗ: от начала сегодняшних суток
до начала следующего календарного месяца в зоне педагога. Прошедшие дни
текущего месяца не считаются: потерять можно только то время, которое ещё
впереди.

Доход по типам занятий (`type_split`) делит **начисленный** доход на
«Индивидуальные» и «Групповые»: тип берётся из урока, на который ссылается
списание, а списания без `lesson_id` (внесённые вручную, без привязки)
относятся к индивидуальным — иначе сумма колонок не сошлась бы с карточкой
«Доход». Групповой урок в часах считается один раз (это время педагога), а
в выручке — всей суммой участников: RevPTH группы поэтому честно показывает
доход с часа.

Сервис не знает про FastAPI: на вход — сессия, репетитор и границы окна,
на выход — готовые к печати словари.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_day_bounds, today_local
from app.finance.models.account_operation import AccountOperation
from app.finance.services.presentation import (
    duration_label,
    free_hours_phrase,
    rate_label,
    ratio_label,
)
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.stats.services.availability import available_minutes
from app.stats.services.hours import MINUTES_PER_HOUR, completed_minutes, planned_minutes
from app.student.models.student import Student

# Ключи типов занятий в контексте шаблона и их подписи-колонки.
TYPE_INDIVIDUAL = "individual"
TYPE_GROUP = "group"

TYPE_LABELS = {
    TYPE_INDIVIDUAL: "Индивидуальные",
    TYPE_GROUP: "Групповые",
}

# Ссылка кнопки «Посмотреть свободные окна» блока простоя.
CALENDAR_URL = "/tutor/calendar"

def rev_per_hour(earned: int, minutes: int) -> int | None:
    """Средняя стоимость астрономического часа; часов нет — `None`.

    `None`, а не ноль: «0 ₽/ч» выглядел бы как измеренное значение, а не
    как отсутствие данных (правило показа нулей).
    """
    if minutes <= 0:
        return None
    return round(earned / (minutes / MINUTES_PER_HOUR))

def time_context(db: Session, tutor, *, earned: int, start, end) -> dict:
    """Проведённые часы периода, их подпись и средняя стоимость часа.

    Часы берутся из того же источника, что «Статистика» (`completed_minutes`),
    поэтому числа разделов не расходятся. RevPTH считается по начисленному
    доходу: его передаёт `summary_context`, чтобы деньги не считались дважды.
    """
    minutes = completed_minutes(db, tutor.id, start=start, end=end)
    rev = rev_per_hour(earned, minutes)
    return {
        "minutes": minutes,
        "duration_label": duration_label(minutes),
        "rev_per_hour": rev,
        "rev_per_hour_label": rate_label(rev),
    }

def free_minutes(db: Session, tutor, *, start: datetime, end: datetime) -> int:
    """Свободные минуты окна: доступное минус занятое, не ниже нуля.

    Занятое — проведённые и запланированные уроки: любое занятие держит
    окно в расписании. Переработка (занято больше, чем доступно по
    шаблону) даёт ноль свободных часов, а не отрицательное значение:
    «минус два свободных часа» — не данные, а ошибка знака.
    """
    available = available_minutes(db, tutor, start=start, end=end)
    busy = completed_minutes(db, tutor.id, start=start, end=end) + planned_minutes(
        db, tutor.id, start=start, end=end
    )
    return max(0, available - busy)

def idle_window(tutor) -> tuple[datetime, datetime]:
    """Окно простоя: начало сегодняшних суток — начало следующего месяца.

    Границы строятся настенным временем педагога (`local_day_bounds`), а не
    сдвигом UTC: на переходе часов окно иначе уехало бы на час.
    """
    today = today_local(tutor)
    start = local_day_bounds(today, tutor)[0]
    first_of_next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    end = local_day_bounds(first_of_next_month, tutor)[0]
    return start, end

def idle_context(db: Session, tutor, *, rev: int | None) -> dict:
    """Блок «Упущенная выручка»: свободные часы, их цена и подписи.

    Сумма появляется только когда есть и свободные часы, и RevPTH: без
    одного из множителей «~0 ₽» соврал бы о размере потерь. Тогда блок всё
    равно называет свободные часы и предлагает открыть расписание — данные
    не прячутся, просто сумма не выдумывается.
    """
    start, end = idle_window(tutor)
    minutes = free_minutes(db, tutor, start=start, end=end)
    lost = round(minutes / MINUTES_PER_HOUR * rev) if minutes > 0 and rev else None
    return {
        "minutes": minutes,
        "hours_phrase": free_hours_phrase(minutes),
        "lost": lost,
        "has_loss": lost is not None and lost > 0,
        "rev_label": rate_label(rev),
        "calendar_url": CALENDAR_URL,
    }

def _group_earned(db: Session, tutor_id: str, *, start, end) -> int:
    """Начисленный доход групповых занятий за период — одним запросом.

    Внутреннее соединение со `lessons` отбрасывает списания без урока: у них
    типа нет, и они относятся к индивидуальным (см. `type_split`).
    """
    conditions = [
        Student.tutor_id == tutor_id,
        AccountOperation.kind == "lesson",
        Lesson.group_id.is_not(None),
    ]
    if start is not None:
        conditions.append(AccountOperation.occurred_at >= start)
    if end is not None:
        conditions.append(AccountOperation.occurred_at < end)

    stmt = (
        select(func.coalesce(func.sum(AccountOperation.amount), 0))
        .select_from(AccountOperation)
        .join(Student, Student.id == AccountOperation.student_id)
        .join(Lesson, Lesson.id == AccountOperation.lesson_id)
        .where(*conditions)
    )
    return int(db.scalar(stmt) or 0)

def _minutes_by_type(db: Session, tutor_id: str, *, start, end) -> dict[str, int]:
    """Проведённые минуты по типам: групповой урок входит один раз.

    Владелец выводится из цели (у урока нет своей колонки `tutor_id`),
    поэтому обе связи — внешние: у индивидуального урока нет группы, у
    группового — ученика, и внутреннее соединение потеряло бы половину.
    """
    is_group = Lesson.group_id.is_not(None)
    conditions = [
        or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
        Lesson.status == "completed",
    ]
    if start is not None:
        conditions.append(Lesson.starts_at >= start)
    if end is not None:
        conditions.append(Lesson.starts_at < end)

    rows = db.execute(
        select(is_group, func.coalesce(func.sum(Lesson.duration_min), 0))
        .select_from(Lesson)
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(*conditions)
        .group_by(is_group)
    ).all()

    result = {TYPE_INDIVIDUAL: 0, TYPE_GROUP: 0}
    for grouped, minutes in rows:
        result[TYPE_GROUP if grouped else TYPE_INDIVIDUAL] = int(minutes)
    return result

def type_split(db: Session, tutor, *, earned: int, start, end) -> list[dict]:
    """Доходы по типам занятий: выручка, часы и средняя стоимость часа.

    Сумма колонок «выручка» равна карточке «Доход»: групповую часть считает
    запрос, индивидуальная — остаток (`earned − группа`), поэтому списания
    без урока не теряются и не удваиваются.
    """
    group_earned = _group_earned(db, tutor.id, start=start, end=end)
    minutes = _minutes_by_type(db, tutor.id, start=start, end=end)
    revenues = {
        TYPE_GROUP: group_earned,
        TYPE_INDIVIDUAL: earned - group_earned,
    }

    columns = []
    for key in (TYPE_INDIVIDUAL, TYPE_GROUP):
        rate = rev_per_hour(revenues[key], minutes[key])
        columns.append(
            {
                "key": key,
                "label": TYPE_LABELS[key],
                "earned": revenues[key],
                "duration_label": duration_label(minutes[key]),
                "minutes": minutes[key],
                "rate": rate,
                "rate_label": rate_label(rate),
            }
        )
    return columns

def type_insight(columns: list[dict]) -> str | None:
    """Подсказка о выгодном типе занятий; сравнивать нечего — `None`.

    Инсайт появляется только когда у групповых RevPTH строго выше, а у
    обоих типов есть и часы, и выручка: иначе деление на ноль и «в 0 раз
    больше» — шум, а не совет.
    """
    by_key = {column["key"]: column for column in columns}
    group = by_key.get(TYPE_GROUP)
    individual = by_key.get(TYPE_INDIVIDUAL)
    if group is None or individual is None:
        return None
    if not group["rate"] or not individual["rate"]:
        return None
    if group["rate"] <= individual["rate"]:
        return None

    ratio = group["rate"] / individual["rate"]
    return (
        f"Групповые занятия приносят вам в {ratio_label(ratio)} больше денег "
        "за час времени. Стоит набрать ещё одну группу."
    )
