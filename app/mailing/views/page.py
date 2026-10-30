"""Страница «Коммуникации» (/tutor/mailings): вкладки «Новое сообщение» и «История»."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.mailing.services.access import require_tutor_id
from app.mailing.services.page import tab_context, tabs_context
from app.mailing.services.page_context import page_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

MAILINGS_URL = "/tutor/mailings"


@router.get(MAILINGS_URL, response_class=HTMLResponse)
def mailings_page(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Страница рассылок; вкладка — query-параметр (`?tab=history`)."""
    tutor = db.get(Tutor, tutor_id)
    tab = request.query_params.get("tab", "")
    context = page_context(db, request, tutor_id, tutor=tutor)
    context.update(tabs_context(tab))
    context.update(
        tab_context(
            db,
            tutor_id,
            tab,
            q=request.query_params.get("q", ""),
            segment=request.query_params.get("segment", ""),
        )
    )
    return templates.TemplateResponse(request, "mailing/index.html", context)
