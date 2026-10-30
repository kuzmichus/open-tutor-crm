"""Партиал панели «Текст сообщения» (перечитывается после правки шаблонов)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.mailing.services.access import require_tutor_id
from app.mailing.services.compose import compose_context
from app.templating import templates

router = APIRouter()

COMPOSER_URL = "/tutor/mailings/composer"


@router.get(COMPOSER_URL, response_class=HTMLResponse)
def composer_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Панель композера; текст сообщения живёт в Alpine-состоянии страницы.

    Сервер отдаёт пустое поле: после события `templates-saved` фабрика
    подставит в него актуальный текст пользователя, ничего не потеряв.
    """
    context = {
        **compose_context(db, tutor_id, q="", segment=""),
        "form_text": "",
        "send_summary": None,
        "send_errors": [],
    }
    return templates.TemplateResponse(request, "mailing/_composer.html", context)
