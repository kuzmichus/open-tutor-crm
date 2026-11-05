"""Сохранение личных данных (вкладка «Профиль», POST).

Ошибка — ре-рендер вкладки с сообщениями; успех — 303 обратно на
вкладку с плашкой сохранения.

Одно действие пишет две таблицы: личные данные — в карточку `Tutor`,
параметры НПД — в `tutor_settings` (через ленивый upsert `save_settings`).
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
from app.tutor.services.settings import save_settings

router = APIRouter()


@router.post("/tutor/profile/save", response_class=HTMLResponse)
def profile_save(
    request: Request,
    name: str = Form(""),
    phone: str = Form(""),
    about: str = Form(""),
    hourly_rate: str = Form(""),
    experience: str = Form(""),
    is_npd_payer: str = Form(""),
    npd_rate_individual: str = Form(""),
    npd_rate_legal: str = Form(""),
    npd_income_limit: str = Form(""),
    npd_present: str = Form(""),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет личные данные и параметры НПД вошедшего репетитора."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = {
        "name": name,
        "phone": phone,
        "about": about,
        "hourly_rate": hourly_rate,
        "experience": experience,
        "is_npd_payer": is_npd_payer,
        "npd_rate_individual": npd_rate_individual,
        "npd_rate_legal": npd_rate_legal,
        "npd_income_limit": npd_income_limit,
        "npd_present": npd_present,
    }
    values, settings_values, errors = parse_profile_form(form)
    if errors:
        context = profile_page_context(
            db, tutor, tab="profile", errors=errors, form=form,
        )
        return templates.TemplateResponse(request, "tutor/profile.html", context)

    for field, value in values.items():
        setattr(tutor, field, value)
    db.commit()
    if settings_values is not None:
        save_settings(db, tutor_id, settings_values)

    return RedirectResponse(url="/tutor/profile?tab=profile&saved=1", status_code=303)