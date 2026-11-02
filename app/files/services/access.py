"""Доступ к скачиванию файла (спека file-storage, design D6).

Актор определяется по трём независимым сессиям — репетитора, ученика и
родителя: у каждой своя cookie и своя таблица, входы не влияют друг на друга.
Правило одно и то же для всех: «чужая запись неотличима от несуществующей»,
поэтому любая неудача — 404, а не 403.

Файл разрешён:

- репетитору-владельцу (`files.tutor_id`);
- ученику — если файл привязан к ДЗ урока, где он цель (индивидуальный урок)
  или участник группы;
- родителю — если файл привязан к ДЗ урока его ребёнка (привязка
  `StudentContact`).

Сервис знает про `Request` и HTTP-исключения: это не доменная логика, а
единственная точка, где три разные модели сессий сводятся к одному правилу
доступа (как `app/common/access.py`).
"""

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.services.contact_sessions import get_contact_id_from_request
from app.cabinet.services.sessions import get_student_id_from_request
from app.files.models.homework_file import HomeworkFile
from app.files.models.stored_file import StoredFile
from app.group.models.group_member import GroupMember
from app.homework.models.homework import Homework
from app.lesson.models.lesson import Lesson
from app.student.models.student_contact import StudentContact
from app.tutor.services.sessions import SessionService

_sessions = SessionService()

def _not_found() -> HTTPException:
    """Чужой и несуществующий файл отвечают одинаково."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND)

def _file_homework_ids(db: Session, file_id: str) -> list[str]:
    """ДЗ, к которым привязан файл (обычно одно, но связь не уникальна)."""
    return list(
        db.scalars(
            select(HomeworkFile.homework_id).where(
                HomeworkFile.file_id == file_id
            )
        ).all()
    )

def _student_can_read(db: Session, file_id: str, student_id: str) -> bool:
    """Файл привязан к ДЗ урока этого ученика (личного или группового)."""
    homework_ids = _file_homework_ids(db, file_id)
    if not homework_ids:
        return False
    lessons = db.execute(
        select(Lesson.student_id, Lesson.group_id)
        .join(Homework, Homework.lesson_id == Lesson.id)
        .where(Homework.id.in_(homework_ids))
    ).all()
    for lesson_student_id, group_id in lessons:
        if lesson_student_id == student_id:
            return True
        if group_id is not None:
            member = db.scalars(
                select(GroupMember.id).where(
                    GroupMember.group_id == group_id,
                    GroupMember.student_id == student_id,
                )
            ).first()
            if member is not None:
                return True
    return False

def _contact_can_read(db: Session, file_id: str, contact_id: str) -> bool:
    """Файл привязан к ДЗ урока ребёнка, привязанного к этому контакту."""
    homework_ids = _file_homework_ids(db, file_id)
    if not homework_ids:
        return False
    lessons = db.execute(
        select(Lesson.student_id, Lesson.group_id)
        .join(Homework, Homework.lesson_id == Lesson.id)
        .where(Homework.id.in_(homework_ids))
    ).all()
    for lesson_student_id, group_id in lessons:
        students: list[str] = []
        if lesson_student_id:
            students.append(lesson_student_id)
        if group_id is not None:
            students.extend(
                db.scalars(
                    select(GroupMember.student_id).where(
                        GroupMember.group_id == group_id
                    )
                ).all()
            )
        if not students:
            continue
        link = db.scalars(
            select(StudentContact.id).where(
                StudentContact.contact_id == contact_id,
                StudentContact.student_id.in_(students),
            )
        ).first()
        if link is not None:
            return True
    return False

def resolve_downloadable_file(
    db: Session, file_id: str, request: Request
) -> StoredFile:
    """Файл, доступный текущему актору; иначе 404.

    Порядок проверок: репетитор (самый частый случай), затем ученик и
    родитель. Ранний выход на первом совпадении — не оптимизация ради
    скорости, а читаемость: каждая ветка проверяет свой вид владения.
    """
    file = db.get(StoredFile, file_id)
    if file is None:
        raise _not_found()

    tutor_id = _sessions.get_tutor_id_from_request(db, request)
    if tutor_id is not None and tutor_id == file.tutor_id:
        return file

    student_id = get_student_id_from_request(db, request)
    if student_id is not None and _student_can_read(db, file.id, student_id):
        return file

    contact_id = get_contact_id_from_request(db, request)
    if contact_id is not None and _contact_can_read(db, file.id, contact_id):
        return file

    raise _not_found()
