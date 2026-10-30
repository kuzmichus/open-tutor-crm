"""Создание шаблона (POST).

Ошибка возвращает форму с сообщениями и введёнными значениями; успех —
пустое тело с событием `templates-saved`: селект «Шаблон» перечитывает
партиал композера. Без `HX-Request` — 303 на страницу рассылок.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed, is_htmx
from app.database import get_db
from app.mailing.services.access import require_tutor_id
from app.mailing.services.templates import create_template
from app.templating import templates

router = APIRouter()

MAILINGS_URL = "/tutor/mailings"


@router.post("/tutor/mailings/templates", response_class=HTMLResponse)
async def create_template_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт шаблон репетитора; `tutor_id` — только из сессии."""
    form = await request.form()

    errors = create_template(
        db,
        tutor_id,
        {"title": form.get("title", ""), "text": form.get("text", "")},
    )
    if errors:
        context = {
            "template": None,
            "template_form": {
                "title": form.get("title", ""),
                "text": form.get("text", ""),
            },
            "template_errors": errors,
        }
        return templates.TemplateResponse(
            request, "mailing/_template_form.html", context
        )

    if not is_htmx(request):
        return RedirectResponse(url=MAILINGS_URL, status_code=303)
    return dialog_closed("templates-saved")
