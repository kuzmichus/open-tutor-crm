"""Выход из системы: завершение сессии."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.tutor.services.sessions import COOKIE_NAME, SessionService, clear_session_cookie

router = APIRouter()

_sessions = SessionService()


@router.post("/tutor/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """Удаляет сессию, сбрасывает cookie и возвращает на страницу входа."""
    _sessions.delete(db, request.cookies.get(COOKIE_NAME))
    response = RedirectResponse(url="/tutor/login", status_code=303)
    clear_session_cookie(response)
    return response
