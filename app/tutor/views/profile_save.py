"""Сохранение личных данных (вкладка «Профиль», POST).

Ошибка — ре-рендер вкладки с сообщениями; успех — 303 обратно на
вкладку с плашкой сохранения.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.profile_form import parse_profile_form
from app.tutor.services.profile_page import profile_page_context

router = APIRouter()


@router.post("/tutor/profile/save", response_class=HTMLResponse)
def profile_save(
    request: Request,
    name: str = Form(""),
    phone: str = Form(""),
    about: str = Form(""),
    hourly_rate: str = Form(""),
    experience: str = Form(""),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет личные данные вошедшего репетитора."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = {
        "name": name,
        "phone": phone,
        "about": about,
        "hourly_rate": hourly_rate,
        "experience": experience,
    }
    values, errors = parse_profile_form(form)
    if errors:
        context = profile_page_context(
            db, tutor, tab="profile", errors=errors, form=form,
        )
        return templates.TemplateResponse(request, "tutor/profile.html", context)

    for field, value in values.items():
        setattr(tutor, field, value)
    db.commit()

    return RedirectResponse(url="/tutor/profile?tab=profile&saved=1", status_code=303)
