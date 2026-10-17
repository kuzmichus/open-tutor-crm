"""Вход репетитора в систему: форма и проверка пароля."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.password_hasher import PasswordHasher
from app.tutor.services.sessions import SessionService, set_session_cookie

router = APIRouter()

# Единое сообщение: не раскрываем, какая из причин не совпала (email или пароль).
INVALID_CREDENTIALS = "Неверный email или пароль"

_sessions = SessionService()
_hasher = PasswordHasher()


def _render(request: Request, error: str | None = None, notice: str | None = None):
    return templates.TemplateResponse(
        request, "tutor/login.html", {"error": error, "notice": notice}
    )


@router.get("/tutor/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    """Страница со формой входа."""
    notice = None
    if request.query_params.get("registered") == "1":
        notice = "Аккаунт создан, войдите."
    elif request.query_params.get("reset") == "1":
        notice = "Пароль изменён, войдите."
    return _render(request, notice=notice)


@router.post("/tutor/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    """Проверяет пароль и открывает сессию (cookie)."""
    tutor = db.scalars(
        select(Tutor).where(Tutor.email == email.strip())
    ).one_or_none()

    if tutor is None or not _hasher.verify(password, tutor.password_hash):
        return _render(request, error=INVALID_CREDENTIALS)

    token = _sessions.create(db, tutor.id)
    response = RedirectResponse(url="/tutor/", status_code=303)
    set_session_cookie(response, token)
    return response
