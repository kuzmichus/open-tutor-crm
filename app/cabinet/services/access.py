"""Доступ к кабинетам: `require_student_id`/`require_contact_id` и редиректы на вход.

По образцу `app/common/access.py` (`require_tutor_id`): страницы кабинета
получают идентификатор актёра только из сессии — никогда из формы или
адреса. Нет сессии → запрос прерывается редиректом на соответствующую
страницу входа до рендера. Здесь же доменный хелпер доступа к одной записи
ученического кабинета: владение ДЗ выводится через урок (у `homework`
своего ученика нет), как у репетитора — через JOIN в `lesson/services/access.py`.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.services.contact_sessions import get_contact_id_from_request
from app.cabinet.services.sessions import get_student_id_from_request
from app.database import get_db
from app.group.models.group_member import GroupMember
from app.homework.models.homework import Homework
from app.lesson.models.lesson import Lesson

STUDENT_LOGIN_URL = "/student/login"
# Кабинет родителя — своя поверхность со своей страницей входа; редирект
# на неё отличим от ученического и не уводит родителя на чужой кабинет.
CONTACT_LOGIN_URL = "/parent/login"


class StudentLoginRequired(HTTPException):
    """Нет действующей сессии ученика: редирект на вход в кабинет."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": STUDENT_LOGIN_URL},
        )


class ContactLoginRequired(HTTPException):
    """Нет действующей сессии контакта: редирект на вход родителя."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": CONTACT_LOGIN_URL},
        )


def require_student_id(
    request: Request,
    db: Session = Depends(get_db),
) -> str:
    """FastAPI-зависимость: id ученика по cookie кабинета либо редирект."""
    student_id = get_student_id_from_request(db, request)
    if student_id is None:
        raise StudentLoginRequired()
    return student_id


def require_contact_id(
    request: Request,
    db: Session = Depends(get_db),
) -> str:
    """FastAPI-зависимость: id контакта по cookie `parent_session` либо редирект."""
    contact_id = get_contact_id_from_request(db, request)
    if contact_id is None:
        raise ContactLoginRequired()
    return contact_id


def get_student_homework(
    db: Session, homework_id: str, student_id: str
) -> Homework:
    """ДЗ урока этого ученика либо 404.

    У урока ровно одна цель (XOR): ДЗ видно, если урок индивидуальный
    этого ученика или групповой, куда он входит. Чужое и несуществующее
    ДЗ неразличимы — 404, а не 403: существование чужой записи не
    раскрывается (спека student-cabinet, «Изоляция по ученику»).
    """
    homework = db.scalars(
        select(Homework).where(Homework.id == homework_id)
    ).one_or_none()
    if homework is not None:
        lesson = db.get(Lesson, homework.lesson_id)
        if lesson is not None:
            if lesson.student_id == student_id:
                return homework
            if lesson.group_id is not None:
                member = db.scalars(
                    select(GroupMember).where(
                        GroupMember.group_id == lesson.group_id,
                        GroupMember.student_id == student_id,
                    )
                ).one_or_none()
                if member is not None:
                    return homework
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
