"""Сохранение токенов мессенджеров (вкладка «Мессенджеры», POST).

Пустое значение поля — «отключить»: параметр удаляется из хранилища,
а не сохраняется пустой строкой, чтобы «подключён» оставался строгим
(непустой токен) во всех местах чтения.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.messenger.services.messengers import SUPPORTED, token_key
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.messenger_form import parse_messenger_form
from app.tutor.services.params import delete_param, set_param
from app.tutor.services.settings_page import settings_page_context

router = APIRouter()


@router.post("/tutor/settings/messengers", response_class=HTMLResponse)
def settings_messengers(
    request: Request,
    # По полю на поддерживаемый мессенджер: список закрытый, новые
    # мессенджеры добавляются сюда вместе с отправителем и валидатором.
    telegram_token: str = Form(""),
    max_token: str = Form(""),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет или сбрасывает токены мессенджеров вошедшего репетитора."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = {
        "telegram_token": telegram_token,
        "max_token": max_token,
    }
    values, errors = parse_messenger_form(form)
    if errors:
        context = settings_page_context(
            db, tutor, tab="messengers", errors=errors, form=form,
        )
        return templates.TemplateResponse(request, "tutor/settings.html", context)

    for messenger in SUPPORTED:
        key = token_key(messenger)
        if values[key]:
            set_param(db, tutor_id, key, values[key])
        else:
            delete_param(db, tutor_id, key)

    return RedirectResponse(
        url="/tutor/settings?tab=messengers&saved=1", status_code=303
    )
