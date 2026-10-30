"""Модалка «Шаблоны сообщений»: список с правкой и удалением."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.mailing.services.access import require_tutor_id
from app.mailing.services.templates import list_templates
from app.templating import templates

router = APIRouter()

TEMPLATES_URL = "/tutor/mailings/templates"


@router.get(TEMPLATES_URL, response_class=HTMLResponse)
def templates_dialog(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Диалог со списком шаблонов; открывается кнопкой «Шаблоны»."""
    return templates.TemplateResponse(
        request,
        "mailing/_templates_dialog.html",
        {"templates": list_templates(db, tutor_id)},
    )
