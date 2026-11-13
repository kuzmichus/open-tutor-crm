"""Оповещения ученикам об отмене или переносе одного сохранённого урока.

Даже при «Применить ко всей серии» статус и начало меняются только у
выбранного урока. Оповещение не обещает изменений остальных занятий.
Снимок до редактирования сохраняет исходное время и получателей.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import tutor_zone
from app.group.models.group_member import GroupMember
from app.messenger.models.student_invite import StudentMessengerInvite
from app.messenger.services.messengers import SUPPORTED
from app.messenger.services.send import send_message
from app.student.models.student import Student
from app.tutor.services.clock import as_utc
from app.tutor.services.settings import get_settings


def lesson_change_snapshot(lesson) -> dict:
    """Исходные значения, которые нельзя восстановить после сохранения."""
    return {
        "starts_at": as_utc(lesson.starts_at),
        "status": lesson.status,
        "student_id": lesson.student_id,
        "group_id": lesson.group_id,
    }


def notify_lesson_change(db: Session, tutor, lesson, before: dict) -> None:
    """Отправляет по всем привязанным каналам после коммита урока.

    Отмена имеет приоритет при одновременной правке статуса и начала.
    Повторное сохранение отменённого урока и правки прочих полей молчат.
    Стандартный диспетчер обеспечивает ретраи и журнал, сбой одного канала
    не мешает остальным. Журнал коммитится отдельно от сохранённого урока.
    """
    cancelled = lesson.status == "cancelled" and before["status"] != "cancelled"
    moved = (
        as_utc(lesson.starts_at) != before["starts_at"]
        and lesson.status != "cancelled"
    )
    if not (cancelled or moved):
        return
    if not get_settings(db, tutor.id).notify_cancellation:
        return

    students = select(Student.id).where(Student.id == before["student_id"])
    if before["group_id"]:
        students = select(GroupMember.student_id).where(
            GroupMember.group_id == before["group_id"]
        )
    recipients = db.execute(
        select(Student.timezone, StudentMessengerInvite.messenger,
               StudentMessengerInvite.chat_id)
        .join(StudentMessengerInvite, StudentMessengerInvite.student_id == Student.id)
        .where(
            Student.id.in_(students),
            Student.tutor_id == tutor.id,
            StudentMessengerInvite.tutor_id == tutor.id,
            StudentMessengerInvite.messenger.in_(SUPPORTED),
            StudentMessengerInvite.chat_id.is_not(None),
            StudentMessengerInvite.chat_id != "",
        )
    ).all()
    for timezone, messenger, chat_id in recipients:
        zone = tutor_zone(tutor)
        if timezone:
            try:
                zone = ZoneInfo(timezone)
            except ZoneInfoNotFoundError:
                pass
        old_time = before["starts_at"].astimezone(zone)
        text = f"Урок {old_time:%d.%m.%Y в %H:%M} отменён репетитором."
        if not cancelled:
            new_time = as_utc(lesson.starts_at).astimezone(zone)
            text = (
                f"Урок {old_time:%d.%m.%Y в %H:%M} перенесён репетитором.\n"
                f"Новое время: {new_time:%d.%m.%Y в %H:%M}."
            )
        send_message(db, tutor.id, messenger, chat_id, text)
    db.commit()
