"""Смена email и пароля (вкладка «Безопасность», POST)."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.password_hasher import PasswordHasher
from app.tutor.services.profile_page import profile_page_context
from app.tutor.services.security_form import parse_security_form

router = APIRouter()


@router.post("/tutor/profile/security", response_class=HTMLResponse)
def profile_security(
    request: Request,
    email: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Обновляет email; непустая пара «пароль + повтор» меняет пароль."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = {
        "email": email,
        "new_password": new_password,
        "new_password_confirm": new_password_confirm,
    }
    values, errors = parse_security_form(db, tutor, form)
    if errors:
        # Присланные значения ре-рендерятся, но пароли в форму не
        # возвращаются: поля типа password пустые, как и были.
        context = profile_page_context(
            db, tutor, tab="security", errors=errors,
            form={"email": email, "new_password": "", "new_password_confirm": ""},
        )
        return templates.TemplateResponse(request, "tutor/profile.html", context)

    tutor.email = values["email"]
    if values["new_password"]:
        tutor.password_hash = PasswordHasher().hash(values["new_password"])
    db.commit()

    return RedirectResponse(url="/tutor/profile?tab=security&saved=1", status_code=303)
