"""Регистрация по приглашению контакта: публичная страница `/parent/invite/<token>`.

Форма — только Email и Пароль: без поля имени и без согласий; имя контакта
и дети страницей не показываются (спека parent-cabinet). Недействительный
токен — неизвестный, погашенный или просроченный — даёт одно и то же
сообщение: страница не раскрывает, существовала ли ссылка. Успех привязывает
вход к контакту, открывает сессию родителя и ведёт в кабинет.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.cabinet.services.contact_invites import find_valid_invite
from app.cabinet.services.contact_registration import (
    ERROR_LINK_INVALID,
    register_by_invite,
)
from app.cabinet.services.contact_sessions import create_session, set_contact_cookie
from app.database import get_db
from app.templating import templates

router = APIRouter()

# Единое сообщение для всех причин недействительности: страница не
# раскрывает, существовала ли ссылка.
INVALID_LINK = (
    "Ссылка недействительна или устарела. Попросите репетитора отправить новую."
)


def _render(
    request: Request,
    *,
    token: str = "",
    error: str | None = None,
    errors: list[str] | None = None,
    email_value: str = "",
    show_form: bool = True,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "cabinet/parent/register.html",
        {
            "token": token,
            "error": error,
            "errors": errors or [],
            "email_value": email_value,
            "show_form": show_form,
        },
    )


@router.get("/parent/invite/{token}", response_class=HTMLResponse)
def register_form(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Форма регистрации родителя; по недействующей ссылке — только сообщение."""
    if find_valid_invite(db, token) is None:
        return _render(request, error=INVALID_LINK, show_form=False)
    return _render(request, token=token)


@router.post("/parent/invite/{token}", response_class=HTMLResponse)
def register_submit(
    request: Request,
    token: str,
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Создаёт или обновляет вход контакта и погашает ссылку (D2).

    Успех — сессия родителя и редирект в кабинет. Если ссылка перестала
    действовать между показом формы и отправкой (перевыпуск, гонка двух
    вкладок), показывается страница недействительной ссылки.
    """
    invite = find_valid_invite(db, token)
    if invite is None:
        return _render(request, error=INVALID_LINK, show_form=False)

    errors = register_by_invite(db, invite, email, password)
    if errors == [ERROR_LINK_INVALID]:
        return _render(request, error=INVALID_LINK, show_form=False)
    if errors:
        return _render(
            request,
            token=token,
            errors=errors,
            email_value=email.strip(),
        )

    session_token = create_session(db, invite.contact_id)
    response = RedirectResponse(url="/parent", status_code=303)
    set_contact_cookie(response, session_token)
    return response
