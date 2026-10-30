"""Вход в кабинет родителя: email + пароль (change parent-cabinet).

У входа контакта одна идентичность — email (колонки `login` нет, design
D1), поэтому и форма без выбора «логин или email». Неверная пара даёт
общее сообщение без уточнения, какой из компонентов не совпал.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.models.contact_access import ContactAccess
from app.cabinet.services.contact_sessions import create_session, set_contact_cookie
from app.database import get_db
from app.templating import templates
from app.tutor.services.password_hasher import PasswordHasher

router = APIRouter()

# Единое сообщение: не раскрываем, какая из причин не совпала
# (email или пароль).
INVALID_CREDENTIALS = "Неверный email или пароль"

_hasher = PasswordHasher()


def _render(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "cabinet/parent/login.html", {"error": error}
    )


@router.get("/parent/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    """Страница входа в кабинет родителя."""
    return _render(request)


@router.post("/parent/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Проверяет пару email/пароль и открывает сессию контакта."""
    access = db.scalars(
        select(ContactAccess).where(ContactAccess.email == email.strip())
    ).one_or_none()

    if access is None or not _hasher.verify(password, access.password_hash):
        return _render(request, error=INVALID_CREDENTIALS)

    token = create_session(db, access.contact_id)
    response = RedirectResponse(url="/parent", status_code=303)
    set_contact_cookie(response, token)
    return response
