"""Вход репетитора в систему: форма и проверка пароля."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.password_hasher import PasswordHasher
from app.tutor.services.registration_mode import is_first_run, registration_open
from app.tutor.services.sessions import SessionService, set_session_cookie

router = APIRouter()

# Единое сообщение: не раскрываем, какая из причин не совпала (email или пароль).
INVALID_CREDENTIALS = "Неверный email или пароль"

_sessions = SessionService()
_hasher = PasswordHasher()


def _render(
    request: Request,
    db: Session,
    error: str | None = None,
    notice: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "tutor/login.html",
        {
            "error": error,
            "notice": notice,
            # В сингл-режиме после первого запуска ссылки на регистрацию
            # ведут в 404 — их не показываем (design D5).
            "show_register": registration_open(db),
        },
    )


@router.get("/tutor/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Страница со формой входа.

    Сингл-режим на первом запуске: репетиторов ещё нет, войти некому —
    отправляем владельца на регистрацию единственного аккаунта (design D3).
    """
    if is_first_run(db):
        return RedirectResponse(url="/tutor/register", status_code=303)

    notice = None
    if request.query_params.get("registered") == "1":
        notice = "Аккаунт создан, войдите."
    elif request.query_params.get("reset") == "1":
        notice = "Пароль изменён, войдите."
    return _render(request, db, notice=notice)


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
        return _render(request, db, error=INVALID_CREDENTIALS)

    token = _sessions.create(db, tutor.id)
    response = RedirectResponse(url="/tutor/", status_code=303)
    set_session_cookie(response, token)
    return response
