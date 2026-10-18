"""Доступ к страницам учеников: сессия репетитора и скоуп по `tutor_id`.

Все вьюхи модуля получают `tutor_id` только отсюда — никогда из формы или
query-параметра. Отсутствие сессии прерывает запрос редиректом на вход.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.models.student import Student
from app.tutor.services.sessions import SessionService

LOGIN_URL = "/tutor/login"

_sessions = SessionService()


class LoginRequired(HTTPException):
    """Нет действующей сессии: запрос прерывается редиректом на вход."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": LOGIN_URL},
        )


def require_tutor_id(
    request: Request,
    db: Session = Depends(get_db),
) -> str:
    """FastAPI-зависимость: `tutor_id` вошедшего репетитора либо редирект."""
    tutor_id = _sessions.get_tutor_id_from_request(db, request)
    if tutor_id is None:
        raise LoginRequired()
    return tutor_id


def get_owned_student(db: Session, student_id: str, tutor_id: str) -> Student:
    """Ученик этого репетитора либо 404.

    Единое правило выборки одного ученика: `id` и `tutor_id` проверяются
    одним запросом. Чужой ученик и несуществующий неразличимы — 404, а не
    403 и не пустая страница: существование чужой записи не раскрывается.
    """
    student = db.scalars(
        select(Student).where(
            Student.id == student_id,
            Student.tutor_id == tutor_id,
        )
    ).one_or_none()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return student
