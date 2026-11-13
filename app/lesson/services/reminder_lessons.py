"""Данные для напоминаний о начале урока: ближайшие уроки с получателями.

Выборка состоит из двух частей:

1. **Новые напоминания** — запланированные уроки в окне максимального
   интервала из `REMINDER_OFFSETS` (24 часа). Нижней границы нет:
   просроченный тик догоняется следующим прогоном, а постановка не задаёт
   предела длительности простоя — напоминание обязано уйти первым же
   прогоном, даже если урок уже начался. Решение «какой интервал
   отправлять» принимает сервис отправки: он сравнивает момент прогона
   с `starts_at`.
2. **Повторы** — уроки, которые уже не «Запланированы» (их закрыло
   автозавершение), но в `lesson_reminders` остались недоставленные
   каналы. Без этой части сбойная доставка терялась бы навсегда: после
   простоя дольше суток автозавершение переводит урок в «Проведён», и
   фильтр по статусу больше никогда не показал бы его. Такие уроки
   помечаются `retry_only` — новых захватов по ним не создаётся, только
   досылаются уже захваченные каналы.

Владелец урока выводится из цели (у `lessons` нет `tutor_id`) — та же
схема, что в дневной сводке. Отменённый и перенесённый уроки не попадают
в выборку ни в одной из частей: напоминание о несостоявшемся занятии не
нужно, даже если до отмены канал не успел доставить сообщение.

Сервис не знает про FastAPI и мессенджеры: на вход — сессия и карточка
педагога, на выход — уроки с получателями-учениками.
"""

from datetime import datetime, timedelta

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_reminder import LessonReminder
from app.lesson.services.reminder_lesson import ReminderLesson
from app.lesson.services.reminder_student import ReminderStudent
from app.student.models.student import Student
from app.tutor.models.tutor_settings import REMINDER_OFFSETS
from app.tutor.services.clock import as_utc

# Статус урока, по которому вообще имеет смысл напоминать: план, а не итог.
REMINDER_STATUS = "planned"

# Статус, в котором урок уже не «Запланирован», но напоминание всё ещё
# имеет смысл досылать: «Проведён» ставит автозавершение, и оно не должно
# отменять незавершённую доставку. «Отменён» и «Перенесён» сюда не входят
# (см. `NOT_HELD_STATUSES` в модели урока): занятие сознательно не
# состоялось, и напоминание о нём не отправляется даже после сбоя канала.
REMINDER_RETRY_STATUSES = ("completed",)

# Горизонт выборки — максимальный интервал настроек.
MAX_OFFSET_MIN = max(REMINDER_OFFSETS)


def _has_pending_delivery():
    """У урока есть канал, захваченный, но не подтверждённый доставкой."""
    return exists().where(
        LessonReminder.lesson_id == Lesson.id,
        LessonReminder.delivered_at.is_(None),
    )


def _full_name(first_name: str | None, last_name: str | None) -> str:
    """«Иван Иванов» — имя ученика одной строкой."""
    return " ".join(part for part in (first_name or "", last_name or "") if part)


def _group_students(
    db: Session, tutor_id: str, group_ids: set[str]
) -> dict[str, tuple[ReminderStudent, ...]]:
    """Участники групп с включёнными напоминаниями одним запросом.

    Фильтр по `tutor_id` обязателен: членство в группе не гарантирует
    того же владельца (состав мог остаться от прошлого владельца), и
    чужой ученик не должен получить напоминание.
    """
    if not group_ids:
        return {}
    rows = db.execute(
        select(
            GroupMember.group_id,
            Student.id,
            Student.first_name,
            Student.last_name,
            Student.timezone,
        )
        .join(Student, Student.id == GroupMember.student_id)
        .where(
            GroupMember.group_id.in_(group_ids),
            Student.tutor_id == tutor_id,
            Student.remind_lesson.is_(True),
        )
        .order_by(Student.first_name, Student.last_name, Student.id)
    ).all()
    result: dict[str, list[ReminderStudent]] = {}
    for group_id, student_id, first_name, last_name, timezone in rows:
        result.setdefault(group_id, []).append(
            ReminderStudent(
                student_id=student_id,
                name=_full_name(first_name, last_name),
                timezone=timezone,
            )
        )
    return {group_id: tuple(items) for group_id, items in result.items()}


def upcoming_lessons(
    db: Session,
    tutor_id: str,
    now: datetime,
) -> list[ReminderLesson]:
    """Уроки с напоминаниями к отправке или повтору, по времени начала.

    `now` — момент проверки в UTC. Уроков нет — пустой список: напоминать
    не о чем, и сеть не дёргается. Верхняя граница — горизонт настроек,
    нижней нет: урок, который уже начался, остаётся в выборке, чтобы
    пропущенный тик был догнан первым же прогоном после простоя (постановка
    не ограничивает его длительность).

    Урок в статусе «Проведён» попадает в выборку, только если в
    `lesson_reminders` остались недоставленные каналы: автозавершение
    закрывает урок через сутки после окончания и не должно отменять
    повтор сбойной доставки. Такой урок помечается `retry_only` — по нему
    досылаются только уже захваченные каналы. Отменённый и перенесённый
    уроки не попадают в выборку ни в одной из частей: напоминание о
    несостоявшемся занятии не отправляется даже после сбоя канала.
    """
    moment = as_utc(now)
    horizon = moment + timedelta(minutes=MAX_OFFSET_MIN)
    rows = db.execute(
        select(
            Lesson,
            Student.first_name,
            Student.last_name,
            Student.timezone,
            Student.remind_lesson,
            Group.name,
        )
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
            Lesson.starts_at <= horizon,
            or_(
                Lesson.status == REMINDER_STATUS,
                and_(
                    Lesson.status.in_(REMINDER_RETRY_STATUSES),
                    _has_pending_delivery(),
                ),
            ),
        )
        .order_by(Lesson.starts_at, Lesson.id)
    ).all()

    group_ids = {lesson.group_id for lesson, *_ in rows if lesson.group_id}
    members = _group_students(db, tutor_id, group_ids)

    lessons: list[ReminderLesson] = []
    for (
        lesson,
        first_name,
        last_name,
        timezone,
        remind_lesson,
        group_name,
    ) in rows:
        if lesson.group_id:
            target_name = group_name or ""
            students = members.get(lesson.group_id, ())
        else:
            target_name = _full_name(first_name, last_name)
            students = (
                ReminderStudent(
                    student_id=lesson.student_id,
                    name=target_name,
                    timezone=timezone,
                ),
            ) if remind_lesson else ()
        lessons.append(
            ReminderLesson(
                lesson_id=lesson.id,
                starts_at=as_utc(lesson.starts_at),
                is_group=bool(lesson.group_id),
                target_name=target_name,
                students=students,
                retry_only=lesson.status != REMINDER_STATUS,
            )
        )
    return lessons
