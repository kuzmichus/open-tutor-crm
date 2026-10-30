"""Выход из кабинета родителя: отзыв сессии контакта."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.cabinet.services.contact_sessions import (
    COOKIE_NAME,
    clear_contact_cookie,
    delete_session,
)
from app.database import get_db

router = APIRouter()


@router.post("/parent/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """Удаляет сессию контакта, сбрасывает cookie `parent_session`, ведёт на вход.

    Cookie репетитора и ученика не затрагиваются: имена и таблицы разные
    (D4) — в одном браузере все три сессии продолжают жить независимо.
    """
    delete_session(db, request.cookies.get(COOKIE_NAME))
    response = RedirectResponse(url="/parent/login", status_code=303)
    clear_contact_cookie(response)
    return response
