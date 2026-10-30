"""Ручка содержимого вкладки страницы рассылок (GET `/tutor/mailings/tabs/{tab}`).

Запрашивается `hx-get` ссылки вкладки: ответ — та же секция
`#mailings-content`, что рендерит страница, поэтому htmx подменяет её
целиком без перезагрузки. Ответ несёт `HX-Push-Url` с каноническим адресом
вкладки: «назад» и перезагрузка открывают ту же вкладку (паттерн финансов).
Неизвестная вкладка в пути — не 404, а «Новое сообщение».
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.mailing.services.access import require_tutor_id
from app.mailing.services.page import page_url, tab_context, tabs_context
from app.mailing.services.page_context import page_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/mailings/tabs/{tab}", response_class=HTMLResponse)
def mailings_tab(
    request: Request,
    tab: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Секция вкладки `tab`; состояние фильтров списка сбрасывается."""
    tutor = db.get(Tutor, tutor_id)
    context = page_context(db, request, tutor_id, tutor=tutor)
    context.update(tabs_context(tab))
    context.update(tab_context(db, tutor_id, tab, q="", segment=""))
    return templates.TemplateResponse(
        request,
        "mailing/_content.html",
        context,
        headers={"HX-Push-Url": page_url(tab)},
    )
