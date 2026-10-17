"""Регистрация репетитора: форма и создание аккаунта."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.password_hasher import PasswordHasher
from app.tutor.services.validation import is_valid_email

router = APIRouter()

# POST принимает только эти поля: имя, email, пароль и его подтверждение.
_EMPTY_FORM = {
    "name": "",
    "email": "",
}


def _render(request: Request, error: str | None, form: dict) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "tutor/register.html", {"error": error, "form": form}
    )


@router.get("/tutor/register", response_class=HTMLResponse)
def register_form(request: Request) -> HTMLResponse:
    """Страница с формой регистрации."""
    return _render(request, None, dict(_EMPTY_FORM))


@router.post("/tutor/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Создаёт аккаунт; при ошибках возвращает ту же форму с сообщением.

    Принимаются только имя, email, пароль и подтверждение пароля.
    Необязательные поля карточки при регистрации не заполняются.
    """
    form = {"name": name, "email": email}

    error = None
    email_clean = email.strip()

    if not name.strip():
        error = "Укажите имя."
    elif not email_clean or not is_valid_email(email_clean):
        error = "Укажите корректный email."
    elif not password:
        error = "Укажите пароль."
    elif password != password_confirm:
        error = "Пароли не совпадают."
    elif db.scalars(select(Tutor).where(Tutor.email == email_clean)).first() is not None:
        error = "Репетитор с таким email уже зарегистрирован."

    if error is not None:
        return _render(request, error, form)

    tutor = Tutor(
        name=name.strip(),
        email=email_clean,
        password_hash=PasswordHasher().hash(password),
    )
    db.add(tutor)
    db.commit()

    return RedirectResponse(url="/tutor/login?registered=1", status_code=303)
