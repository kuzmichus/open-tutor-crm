"""Восстановление пароля: запрос ссылки по email.

Два режима, и выбирает их конфигурация сервера:

- **почта настроена** (`SMTP_HOST`) — на email репетитора уходит письмо со
  ссылкой сброса, а страница показывает нейтральное подтверждение без
  ссылки. Одинаковый текст для существующего и неизвестного email не
  раскрывает, есть ли аккаунт;
- **почта не настроена** — демо-режим: ссылка показывается прямо на
  странице. Так установка «из коробки» не теряет восстановление пароля,
  пока владелец сервера не завёл SMTP.
"""

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.mail.services.sender import email_enabled
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.password_reset import PasswordResetService
from app.tutor.services.password_reset_email import send_password_reset_email
from app.tutor.services.validation import is_valid_email

logger = logging.getLogger("mail")

router = APIRouter()

_reset = PasswordResetService()

# Нейтральное подтверждение: одинаково для существующего и неизвестного
# email, иначе форма превратилась бы в проверку «зарегистрирован ли».
_NEUTRAL_SENT = (
    "Если аккаунт с таким email существует, "
    "письмо со ссылкой для сброса пароля отправлено."
)
_NEUTRAL_DEMO = (
    "Если аккаунт с таким email существует, "
    "ссылка для сброса пароля показана ниже."
)


def _render(request: Request, error: str | None, message: str | None, link: str | None):
    return templates.TemplateResponse(
        request,
        "tutor/remember_password.html",
        {"error": error, "message": message, "link": link},
    )


def _reset_url(request: Request, token: str) -> str:
    """Абсолютная ссылка на страницу нового пароля.

    `APP_BASE_URL` важнее `request.base_url`: за прокси адрес запроса может
    быть `http://` и внутренним хостом, а ссылка в письме должна вести на
    внешний адрес приложения.
    """
    path = f"/tutor/reset-password?key={token}"
    base = settings.app_base_url.strip()
    if base:
        return base.rstrip("/") + path
    return str(request.base_url).rstrip("/") + path


@router.get("/tutor/remember-password", response_class=HTMLResponse)
def remember_password_form(request: Request) -> HTMLResponse:
    """Страница с полем ввода email."""
    return _render(request, error=None, message=None, link=None)


@router.post("/tutor/remember-password", response_class=HTMLResponse)
def remember_password_submit(
    request: Request,
    email: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Создаёт ключ и отправляет ссылку; для неизвестного email — заглушка."""
    email_clean = email.strip()
    if not email_clean or not is_valid_email(email_clean):
        return _render(request, error="Укажите корректный email.", message=None, link=None)

    with_mail = email_enabled()
    tutor = db.scalars(select(Tutor).where(Tutor.email == email_clean)).one_or_none()
    if tutor is None:
        # Нейтральное подтверждение: не раскрываем, существует ли аккаунт.
        return _render(
            request,
            error=None,
            message=_NEUTRAL_SENT if with_mail else _NEUTRAL_DEMO,
            link=None,
        )

    token = _reset.create(db, tutor.id)
    link = _reset_url(request, token)

    if not with_mail:
        return _render(
            request,
            error=None,
            message="Ссылка для сброса пароля (почта не настроена, демо-режим):",
            link=link,
        )

    errors = send_password_reset_email(
        to_email=tutor.email,
        tutor_name=tutor.name,
        reset_url=link,
    )
    if errors:
        # Сбой доставки виден в логах сервера, но не пользователю: сообщение
        # об ошибке раскрыло бы, что аккаунт с таким email существует.
        logger.warning(
            "Письмо восстановления пароля не отправлено (%s): %s",
            email_clean,
            "; ".join(errors),
        )
    return _render(request, error=None, message=_NEUTRAL_SENT, link=None)
