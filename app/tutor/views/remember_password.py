"""Восстановление пароля: запрос ссылки по email."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.password_reset import PasswordResetService
from app.tutor.services.validation import is_valid_email

router = APIRouter()

_reset = PasswordResetService()


def _render(request: Request, error: str | None, message: str | None, link: str | None):
    return templates.TemplateResponse(
        request,
        "tutor/remember_password.html",
        {"error": error, "message": message, "link": link},
    )


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
    """Создаёт ключ и показывает ссылку; для неизвестного email — заглушка."""
    email_clean = email.strip()
    if not email_clean or not is_valid_email(email_clean):
        return _render(request, error="Укажите корректный email.", message=None, link=None)

    tutor = db.scalars(select(Tutor).where(Tutor.email == email_clean)).one_or_none()
    if tutor is None:
        # Нейтральное подтверждение: не раскрываем, существует ли аккаунт.
        return _render(
            request,
            error=None,
            message=(
                "Если аккаунт с таким email существует, "
                "ссылка для сброса пароля показана ниже."
            ),
            link=None,
        )

    token = _reset.create(db, tutor.id)
    link = f"/tutor/reset-password?key={token}"
    return _render(
        request,
        error=None,
        message="Ссылка для сброса пароля (демо-заглушка вместо письма):",
        link=link,
    )
