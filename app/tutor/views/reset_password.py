"""Установка нового пароля по ключу восстановления."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.password_hasher import PasswordHasher
from app.tutor.services.password_reset import PasswordResetService

router = APIRouter()

_reset = PasswordResetService()
_hasher = PasswordHasher()

INVALID_LINK = "Ссылка недействительна или устарела. Запросите новую."


def _render(request: Request, key: str, error: str | None, show_form: bool):
    return templates.TemplateResponse(
        request,
        "tutor/reset_password.html",
        {"key": key, "error": error, "show_form": show_form},
    )


def _show_invalid(request: Request, key: str) -> HTMLResponse:
    return _render(request, key, error=INVALID_LINK, show_form=False)


@router.get("/tutor/reset-password", response_class=HTMLResponse)
def reset_password_form(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Форма нового пароля; по недействующему ключу — сообщение об ошибке."""
    key = request.query_params.get("key", "")
    if _reset.get_tutor_id(db, key) is None:
        return _show_invalid(request, key)
    return _render(request, key, error=None, show_form=True)


@router.post("/tutor/reset-password", response_class=HTMLResponse)
def reset_password_submit(
    request: Request,
    key: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    """Меняет пароль и погашает ключ; пустой пароль — ошибка без смены."""
    tutor_id = _reset.get_tutor_id(db, key)
    if tutor_id is None:
        return _show_invalid(request, key)

    if not password:
        return _render(request, key, error="Укажите новый пароль.", show_form=True)

    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        return _show_invalid(request, key)

    tutor.password_hash = _hasher.hash(password)
    # Ключ погашается в той же транзакции, что и смена пароля.
    _reset.consume(db, key)
    db.commit()

    return RedirectResponse(url="/tutor/login?reset=1", status_code=303)
