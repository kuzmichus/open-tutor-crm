"""Астрономические часы статистики: единый источник длительности.

Глоссарий задачи: «час» — единица длительности (60 минут), а не «занятие» и
не «слот». Один урок 45 минут — это 0,75 часа, 90 минут — 1,5 часа. Поэтому
все часы в модуле считаются из `Lesson.duration_min`, а не из количества
уроков: иначе 45-минутные занятия завышали бы загрузку в полтора раза.

Разделение, зафиксированное здесь и повторяемое в текстах интерфейса:

- **фактические часы** — проведённые уроки (`status="completed"`), включая
  пробные: пробное — реально потраченное время педагога;
- **часы на ученика** — время, проведённое с конкретным учеником; в «Занятий
  в неделю» и «Часов/нед» пробные не участвуют (одна шкала с «Занятий/нед»),
  иначе ученик с единственным пробным выглядел бы регулярным;
- **групповой урок считается один раз** как время педагога: длительность —
  свойство занятия, а не число участников. Участнику группы в «часы на
  ученика» идёт полная длительность — это его время с педагогом, поэтому
  сумма по ученикам может быть больше фактических часов.

Все границы периода — aware-UTC `[start, end)`; `None` означает «без
границы» (всё время), что нужно вкладке «Обзор» с периодом «Всё время».
"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.services.clock import as_utc

MINUTES_PER_HOUR = 60


def minutes_to_hours(minutes: int) -> float:
    """Минуты → астрономические часы (45 мин → 0,75)."""
    return minutes / MINUTES_PER_HOUR


def _lesson_bounds(stmt, *, start: datetime | None, end: datetime | None):
    """Добавляет к запросу границы периода `[start, end)`, если они заданы."""
    if start is not None:
        stmt = stmt.where(Lesson.starts_at >= start)
    if end is not None:
        stmt = stmt.where(Lesson.starts_at < end)
    return stmt


def _owned_lessons(tutor_id: str, status: str):
    """Уроки репетитора нужного статуса — индивидуальные и групповые.

    Владелец выводится из цели (у урока нет своей колонки `tutor_id`),
    поэтому обе связи — внешние: у индивидуального урока нет группы, у
    группового — ученика, и внутреннее соединение потеряло бы половину.
    """
    return (
        select(
            func.coalesce(func.sum(Lesson.duration_min), 0),
        )
        .select_from(Lesson)
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
            Lesson.status == status,
        )
    )


def completed_minutes(
    db: Session,
    tutor_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """Фактические минуты за период: проведённые уроки, включая пробные.

    Групповой урок входит своей длительностью один раз — это время
    педагога, а не сумма времени участников.
    """
    stmt = _lesson_bounds(_owned_lessons(tutor_id, "completed"), start=start, end=end)
    return int(db.scalar(stmt) or 0)


def planned_minutes(
    db: Session,
    tutor_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """Запланированные минуты за период: сумма длительности будущих уроков."""
    stmt = _lesson_bounds(_owned_lessons(tutor_id, "planned"), start=start, end=end)
    return int(db.scalar(stmt) or 0)


def _student_minutes(
    db: Session,
    tutor_id: str,
    *,
    start: datetime | None,
    end: datetime | None,
    regular_only: bool,
) -> dict[str, int]:
    """Минуты по ученикам: индивидуальные плюс групповые через состав групп.

    Участнику группового урока идёт полная длительность занятия — это его
    время с педагогом. `regular_only` отбрасывает пробные: шкала «Занятий/
    нед» и «Часов/нед» считает только регулярные занятия.
    """
    result: dict[str, int] = {}

    def base(stmt, owner):
        """Общие условия: владелец, «проведён» и (для регулярных) не пробное."""
        conditions = [owner == tutor_id, Lesson.status == "completed"]
        if regular_only:
            conditions.append(Lesson.type != "trial")
        return _lesson_bounds(stmt.where(*conditions), start=start, end=end)

    individual = base(
        select(Lesson.student_id, func.coalesce(func.sum(Lesson.duration_min), 0))
        .join(Student, Student.id == Lesson.student_id)
        .group_by(Lesson.student_id),
        Student.tutor_id,
    )
    for student_id, minutes in db.execute(individual).all():
        result[student_id] = int(minutes)

    grouped = base(
        select(
            GroupMember.student_id,
            func.coalesce(func.sum(Lesson.duration_min), 0),
        )
        .join(Lesson, Lesson.group_id == GroupMember.group_id)
        .join(Student, Student.id == GroupMember.student_id)
        .group_by(GroupMember.student_id),
        Student.tutor_id,
    )
    for student_id, minutes in db.execute(grouped).all():
        result[student_id] = result.get(student_id, 0) + int(minutes)
    return result


def student_completed_minutes(
    db: Session,
    tutor_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, int]:
    """«Время на ученика»: минуты с каждым учеником, включая пробные."""
    return _student_minutes(
        db, tutor_id, start=start, end=end, regular_only=False
    )


def student_regular_minutes(
    db: Session,
    tutor_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, int]:
    """Минуты регулярных занятий по ученикам — база «Часов/нед» и флага падения.

    Пробные не считаются: «Часов/нед» должна читаться на одной шкале с
    «Занятий/нед», где пробных тоже нет.
    """
    return _student_minutes(db, tutor_id, start=start, end=end, regular_only=True)


def week_busy_intervals(
    db: Session,
    tutor_id: str,
    *,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, int]]:
    """Интервалы уроков недели для карты загрузки: `(начало UTC, минуты)`.

    Берутся уроки любого статуса: запланированное занятие тоже занимает
    время в расписании, и «свободным» это окно называть нельзя.
    """
    rows = db.execute(
        select(Lesson.starts_at, Lesson.duration_min)
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
        .order_by(Lesson.starts_at)
    ).all()
    return [(as_utc(starts_at), int(duration)) for starts_at, duration in rows]
