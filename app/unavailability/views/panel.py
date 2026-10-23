"""Панель «Отпуск и выходные»: открытие в контейнере `#modal`.

GET отдаёт фрагмент `unavailability/_panel.html` (design.md D8): форму
новой отметки и список «Уже отмечено». Точка входа — пункт меню «⋯» на
панели календаря. Без сессии — редирект на вход (`require_tutor_id`),
разметка панели не отдаётся (спека tutor-unavailability).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.unavailability.services.access import require_tutor_id
from app.unavailability.services.unavailability_form import panel_context

router = APIRouter()


@router.get("/tutor/unavailability", response_class=HTMLResponse)
def unavailability_panel(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Панель недоступности вошедшего репетитора."""
    return templates.TemplateResponse(
        request, "unavailability/_panel.html", panel_context(db, tutor_id)
    )
