"""Партиал списка получателей рассылки (поиск, сегменты, чекбоксы)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.mailing.services.access import require_tutor_id
from app.mailing.services.compose import compose_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

RECIPIENTS_URL = "/tutor/mailings/recipients"


@router.get(RECIPIENTS_URL, response_class=HTMLResponse)
def recipients_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Список с учётом query-фильтров (q, segment); выбор живёт на странице."""
    tutor = db.get(Tutor, tutor_id)
    context = {
        "tutor": tutor,
        **compose_context(
            db,
            tutor_id,
            q=request.query_params.get("q", ""),
            segment=request.query_params.get("segment", ""),
        ),
    }
    return templates.TemplateResponse(request, "mailing/_recipients.html", context)
