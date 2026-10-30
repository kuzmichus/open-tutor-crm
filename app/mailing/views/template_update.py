"""Обновление шаблона (POST).

Тот же контракт, что у создания: ошибка — форма с введёнными значениями,
успех — пустое тело с `templates-saved`, без JS — 303.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed, is_htmx
from app.database import get_db
from app.mailing.services.access import get_owned_template, require_tutor_id
from app.mailing.services.templates import update_template
from app.templating import templates

router = APIRouter()

MAILINGS_URL = "/tutor/mailings"


@router.post("/tutor/mailings/templates/{template_id}", response_class=HTMLResponse)
async def update_template_view(
    request: Request,
    template_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Обновляет свой шаблон; чужой — 404 ещё до чтения формы."""
    template = get_owned_template(db, template_id, tutor_id)
    form = await request.form()

    errors = update_template(
        db,
        template,
        {"title": form.get("title", ""), "text": form.get("text", "")},
    )
    if errors:
        context = {
            "template": template,
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
