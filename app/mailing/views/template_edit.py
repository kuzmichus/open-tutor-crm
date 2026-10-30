"""Форма правки шаблона (GET).

Открывается кнопкой-карандашом в модалке «Шаблоны» (в `#modal` вместо
списка). Чужой или несуществующий шаблон — 404: существование чужой записи
не раскрывается.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.mailing.services.access import get_owned_template, require_tutor_id
from app.templating import templates

router = APIRouter()


@router.get("/tutor/mailings/templates/{template_id}/edit", response_class=HTMLResponse)
def edit_template_dialog(
    request: Request,
    template_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Форма правки с сохранёнными значениями шаблона."""
    template = get_owned_template(db, template_id, tutor_id)
    context = {
        "template": template,
        "template_form": {"title": template.title, "text": template.text},
        "template_errors": [],
    }
    return templates.TemplateResponse(request, "mailing/_template_form.html", context)
