"""Доступ по сессии репетитора: `require_tutor_id` и `LoginRequired`.

Общий код (правило AGENTS.md «общий код — в `common/`»): доступ по сессии
переиспользуется разными доменами (student, calendar и др.), поэтому живёт
здесь, а не внутри модуля student, — новый модуль не получает зависимость
на student. Все вьюхи получают `tutor_id` только отсюда — никогда из формы
или query-параметра. Отсутствие сессии прерывает запрос редиректом на вход.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
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
