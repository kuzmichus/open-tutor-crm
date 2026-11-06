"""Сохранение настроек вкладки «Финансы» (POST).

Пока вкладка содержит один блок — «Налоги»: статус плательщика НПД,
ставки налога для физлиц и юрлиц/ИП и максимально допустимый доход в год.
Значения живут в настройках репетитора (`tutor_settings`) и изолированы
по владельцу: сохраняется только строка вошедшего репетитора.

Поля ставок и лимита при выключенном переключателе отключены (`disabled`),
поэтому браузер их не присылает. В этом случае сохранённые значения не
трогаются: разбор возвращает только сам признак, и после редиректа вкладка
показывает прежние ставки и лимит из настроек.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.finances_form import parse_finances_form
from app.tutor.services.profile_page import profile_page_context
from app.tutor.services.settings import save_settings

router = APIRouter()


@router.post("/tutor/profile/finances", response_class=HTMLResponse)
def profile_finances(
    request: Request,
    npd_enabled: str = Form(""),
    npd_tax_rate_individual: str = Form(""),
    npd_tax_rate_legal_entity: str = Form(""),
    npd_annual_income_limit: str = Form(""),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет настройки НПД вкладки «Финансы»."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = {
        # Переключатель неотмеченным не присылает поле вовсе; пустая строка
        # в `form` нужна, чтобы шаблон при ошибке видел выключенное значение.
        "npd_enabled": npd_enabled,
        "npd_tax_rate_individual": npd_tax_rate_individual,
        "npd_tax_rate_legal_entity": npd_tax_rate_legal_entity,
        "npd_annual_income_limit": npd_annual_income_limit,
    }
    values, errors = parse_finances_form(form)
    if errors:
        context = profile_page_context(
            db, tutor, tab="finances", errors=errors, form=form,
        )
        return templates.TemplateResponse(request, "tutor/profile.html", context)

    save_settings(db, tutor_id, values)
    return RedirectResponse(url="/tutor/profile?tab=finances&saved=1", status_code=303)
