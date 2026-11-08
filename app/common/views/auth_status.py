"""Статус входа по трём сессиям для клиентской подмены кнопок лендинга.

Эндпоинт публичный: он отдаёт только булевы признаки собственных cookie
текущего запроса и не раскрывает чужих данных. `Cache-Control: no-store`
обязателен — иначе вход и выход не были бы видны сразу ни браузеру, ни
прокси.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.cabinet.services.contact_sessions import get_contact_id_from_request
from app.cabinet.services.sessions import get_student_id_from_request
from app.database import get_db
from app.tutor.services.sessions import SessionService

router = APIRouter()

_sessions = SessionService()


@router.get("/auth/status", tags=["auth"])
def auth_status(
    request: Request, db: Session = Depends(get_db)
) -> JSONResponse:
    """Булевы статусы входа ученика, родителя и репетитора.

    Сессии независимы: каждая проверяется по своей cookie, поэтому
    комбинации любые, а отсутствующая или протухшая сессия даёт `false`.
    """
    return JSONResponse(
        {
            "student": get_student_id_from_request(db, request) is not None,
            "parent": get_contact_id_from_request(db, request) is not None,
            "tutor": _sessions.get_tutor_id_from_request(db, request) is not None,
        },
        headers={"Cache-Control": "no-store"},
    )
