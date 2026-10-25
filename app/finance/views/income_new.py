"""Диалог платежа с выбором ученика (GET, design D5 finance-page).

Открывается кнопкой «Доход» страницы финансов в контейнер
`#modal-payment`. От диалога из карточки ученика отличается только полем
«Ученик»: здесь оно пустое, и репетитор выбирает его из списка активных
и новых учеников. Шаблон тот же — `finance/_payment_dialog.html`.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.income_dialog import income_dialog_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/payments/new", response_class=HTMLResponse)
def new_income_dialog(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма платежа с выбором ученика; без сессии — на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    return templates.TemplateResponse(
        request,
        "finance/_payment_dialog.html",
        income_dialog_context(db, tutor),
    )
