"""Диалог расхода (GET, спека tutor-finance «Внесение расхода»).

Открывается кнопкой «Расход» страницы финансов в контейнер
`#modal-expense`: платёж и расход — независимые диалоги, ошибка в одном
не должна перетирать другой. Форма приходит свопом уже открытой (паттерн
`income_new`).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.expense_dialog import expense_dialog_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/expenses/new", response_class=HTMLResponse)
def new_expense_dialog(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма расхода; без сессии — редирект на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        raise LoginRequired()

    return templates.TemplateResponse(
        request,
        "finance/_expense_dialog.html",
        expense_dialog_context(tutor),
    )
