"""Выход из кабинета: отзыв сессии ученика."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.cabinet.services.sessions import (
    COOKIE_NAME,
    clear_student_cookie,
    delete_session,
)
from app.database import get_db

router = APIRouter()


@router.post("/student/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """Удаляет сессию ученика, сбрасывает cookie кабинета, ведёт на вход.

    Cookie репетитора не затрагивается: имя другое, а сессии — разные
    таблицы (D4); в одном браузере обе сессии продолжают жить.
    """
    delete_session(db, request.cookies.get(COOKIE_NAME))
    response = RedirectResponse(url="/student/login", status_code=303)
    clear_student_cookie(response)
    return response
