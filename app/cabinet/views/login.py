"""Вход в личный кабинет: идентификатор (email или логин) + пароль.

Идентификатор с `@` ищется по колонке `email`, без `@` — по `login`
(D1 change'а student-cabinet-access): пространства имён не пересекаются,
потому что логин из ручной модалки не может содержать `@`. Неверная пара
даёт общее сообщение без уточнения, какой из компонентов неверен.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.services.sessions import create_session, set_student_cookie
from app.database import get_db
from app.student.models.student_access import StudentAccess
from app.templating import templates
from app.tutor.services.password_hasher import PasswordHasher

router = APIRouter()

# Единое сообщение: не раскрываем, какая из причин не совпала
# (идентификатор или пароль).
INVALID_CREDENTIALS = "Неверный логин (email) или пароль"

_hasher = PasswordHasher()


def _render(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(request, "cabinet/login.html", {"error": error})


@router.get("/student/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    """Страница входа в кабинет."""
    return _render(request)


@router.post("/student/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    identifier: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Проверяет пароль и открывает сессию ученика (cookie кабинета)."""
    identifier = identifier.strip()
    column = StudentAccess.email if "@" in identifier else StudentAccess.login
    access = db.scalars(
        select(StudentAccess).where(column == identifier)
    ).one_or_none()

    if access is None or not _hasher.verify(password, access.password_hash):
        return _render(request, error=INVALID_CREDENTIALS)

    token = create_session(db, access.student_id)
    response = RedirectResponse(url="/student", status_code=303)
    set_student_cookie(response, token)
    return response
