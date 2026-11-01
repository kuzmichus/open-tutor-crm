"""Данные дневной сводки: уроки дня педагога с целями и ценами.

Сводка — расписание дня, поэтому берутся только «Запланированные» уроки:
проведённое занятие из плана дня уже не актуально, а пометка «не хватает
денег» относится к предстоящей оплате. Отмены и переносы в модели не
представлены отдельными статусами — учитывать нечего.

Владелец урока выводится из цели (у `lessons` нет `tutor_id`), окно дня
считается в зоне педагога — та же схема, что у `dashboard.today_lessons`
(design D3 спеки tutor-timezone).

Цены берутся из единственного правила модуля finance
(`charges.lesson_targets_any_status`): индивидуальный урок — `lesson.price`,
участник группы — `price_override ?? group.price_per_lesson`. Своего
расчёта цены здесь нет — иначе сводка и списания разошлись бы.

Сервис не знает про FastAPI и мессенджеры: на вход — сессия и карточка
педагога, на выход — строки для текста сообщения.
"""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_day_bounds, today_local
from app.finance.services.charges import lesson_targets_any_status
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.lesson.services.digest_lesson import DigestLesson
from app.lesson.services.digest_target import DigestTarget
from app.student.models.student import Student
from app.tutor.services.clock import as_utc

# Статус урока, который попадает в сводку: план дня, а не его итог.
DIGEST_STATUS = "planned"


def _full_name(first_name: str | None, last_name: str | None) -> str:
    """«Иван Иванов» — имя ученика одной строкой."""
    return " ".join(part for part in (first_name or "", last_name or "") if part)


def _names_by_student(db: Session, tutor_id: str, ids: set[str]) -> dict[str, str]:
    """Имена учеников педагога одним запросом: `student_id → имя`.

    Фильтр по `tutor_id` обязателен: членство в группе не гарантирует
    того же владельца (состав мог остаться от прошлого владельца группы),
    и чужой ученик не должен попасть в сводку даже строкой.
    """
    if not ids:
        return {}
    rows = db.execute(
        select(Student.id, Student.first_name, Student.last_name).where(
            Student.id.in_(ids),
            Student.tutor_id == tutor_id,
        )
    ).all()
    return {student_id: _full_name(first_name, last_name) for student_id, first_name, last_name in rows}


def digest_lessons(
    db: Session,
    tutor,
    day: date | None = None,
) -> list[DigestLesson]:
    """Запланированные уроки дня педагога по времени начала.

    `day` — календарная дата в зоне педагога; по умолчанию «сегодня».
    Уроков нет — пустой список: пустую сводку не отправляем.
    """
    start, end = local_day_bounds(day or today_local(tutor), tutor)
    stmt = (
        select(Lesson, Student.first_name, Student.last_name, Group.name)
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(
            or_(Student.tutor_id == tutor.id, Group.tutor_id == tutor.id),
            Lesson.status == DIGEST_STATUS,
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
        .order_by(Lesson.starts_at, Lesson.id)
    )
    rows = db.execute(stmt).all()

    # Цены целей — отдельным проходом: имена участников групп нужны одним
    # запросом на всех, а не по запросу на урок.
    targets_by_lesson = {
        lesson.id: lesson_targets_any_status(db, lesson) for lesson, *_ in rows
    }
    names = _names_by_student(
        db,
        tutor.id,
        {
            student_id
            for targets in targets_by_lesson.values()
            for student_id, _price in targets
        },
    )

    lessons: list[DigestLesson] = []
    for lesson, first_name, last_name, group_name in rows:
        is_group = bool(lesson.group_id)
        target_name = (
            group_name or "" if is_group else _full_name(first_name, last_name)
        )
        targets = tuple(
            DigestTarget(
                student_id=student_id,
                name=names[student_id],
                price=price,
            )
            for student_id, price in targets_by_lesson[lesson.id]
            # Ученик вне списка педагога — не цель сводки (см. `_names_by_student`).
            if student_id in names
        )
        lessons.append(
            DigestLesson(
                starts_at=as_utc(lesson.starts_at),
                target_name=target_name,
                is_group=is_group,
                targets=targets,
            )
        )
    return lessons
