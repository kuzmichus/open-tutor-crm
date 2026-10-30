"""Удаление шаблона (POST).

Успех возвращает обновлённую модалку «Шаблоны» (список без удалённого) и
шлёт `templates-saved` — селект «Шаблон» композера перечитается. Без JS —
303 на страницу рассылок.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import is_htmx
from app.database import get_db
from app.mailing.services.access import get_owned_template, require_tutor_id
from app.mailing.services.templates import delete_template, list_templates
from app.templating import templates

router = APIRouter()

MAILINGS_URL = "/tutor/mailings"


@router.post(
    "/tutor/mailings/templates/{template_id}/delete", response_class=HTMLResponse
)
async def delete_template_view(
    request: Request,
    template_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Удаляет свой шаблон; чужой — 404."""
    template = get_owned_template(db, template_id, tutor_id)
    delete_template(db, template)

    if not is_htmx(request):
        return RedirectResponse(url=MAILINGS_URL, status_code=303)
    response = templates.TemplateResponse(
        request,
        "mailing/_templates_dialog.html",
        {"templates": list_templates(db, tutor_id)},
    )
    response.headers["HX-Trigger"] = "templates-saved"
    return response
