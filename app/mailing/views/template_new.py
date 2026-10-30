"""Форма «Сохранить как шаблон» (GET).

Открывается кнопкой «Сохранить» композера в `#modal`; текущий текст
сообщения передаётся query-параметром `text` (`hx-vals="js:..."` с чтением
textarea). Правка существующего — тот же шаблон формы с `template`.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.mailing.services.access import require_tutor_id
from app.templating import templates

router = APIRouter()


@router.get("/tutor/mailings/templates/new", response_class=HTMLResponse)
def new_template_dialog(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма шаблона с текстом из композера (если был)."""
    context = {
        "template": None,
        "template_form": {"title": "", "text": request.query_params.get("text", "")},
        "template_errors": [],
    }
    return templates.TemplateResponse(request, "mailing/_template_form.html", context)
