"""Соответствие «урок → событие Google»: чтение и запись `calendar_events`.

Строки живут в своей таблице, а не в `tutor_params`: нужен каскад вместе
с уроком и выборка «все события репетитора» одним JOIN. Владелец урока
выводится из цели (`lessons` не хранит `tutor_id`, design D3), поэтому
выборки идут через `students`/`groups`.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.gcalendar.models.calendar_event import CalendarEvent
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.services.clock import utcnow

def get(db: Session, lesson_id: str) -> CalendarEvent | None:
    """Строка соответствия урока или `None`, если события ещё нет."""
    return db.get(CalendarEvent, lesson_id)

def upsert(
    db: Session,
    lesson_id: str,
    *,
    event_id: str,
    calendar_id: str,
    content_hash: str,
) -> CalendarEvent:
    """Создаёт или обновляет строку соответствия (без коммита).

    Коммит делает вызывающая сторона: синхронизация урока не должна
    разрывать транзакцию веб-запроса.
    """
    row = db.get(CalendarEvent, lesson_id)
    if row is None:
        row = CalendarEvent(
            lesson_id=lesson_id,
            event_id=event_id,
            calendar_id=calendar_id,
            content_hash=content_hash,
            synced_at=utcnow(),
        )
        db.add(row)
        return row
    row.event_id = event_id
    row.calendar_id = calendar_id
    row.content_hash = content_hash
    row.synced_at = utcnow()
    return row

def forget(db: Session, lesson_id: str) -> None:
    """Удаляет строку соответствия (без коммита); отсутствие — не ошибка."""
    row = db.get(CalendarEvent, lesson_id)
    if row is not None:
        db.delete(row)

def forget_tutor(db: Session, tutor_id: str) -> int:
    """Удаляет все строки соответствий репетитора. Возвращает число строк.

    Нужно при отключении интеграции: события в Google остаются, а связи
    с ними больше нет — повторное подключение создаст события заново
    (design D11).
    """
    rows = db.scalars(
        _owned_query(tutor_id)
    ).all()
    for row in rows:
        db.delete(row)
    db.commit()
    return len(rows)

def event_ids_of_tutor(db: Session, tutor_id: str) -> dict[str, CalendarEvent]:
    """Все строки соответствий репетитора: «event_id → строка»."""
    rows = db.scalars(_owned_query(tutor_id)).all()
    return {row.event_id: row for row in rows}

def _owned_query(tutor_id: str):
    """Выборка строк соответствий через JOIN по цели урока."""
    return (
        select(CalendarEvent)
        .join(Lesson, CalendarEvent.lesson_id == Lesson.id)
        .outerjoin(Student, Lesson.student_id == Student.id)
        .outerjoin(Group, Lesson.group_id == Group.id)
        .where(or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id))
    )
