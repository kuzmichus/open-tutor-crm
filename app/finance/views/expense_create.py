"""Создание расхода (POST, спека tutor-finance «Внесение расхода»).

`tutor_id` — только из сессии: расход принадлежит репетитору целиком,
ученика у него нет. Ошибки валидации возвращают диалог с сообщениями
и введёнными значениями; успех — пустой ответ с событием `expense-saved`
(сводка, лента операций и карточка балансов перезапрашивают себя).
Без `HX-Request` POST отвечает 303 на страницу финансов — форма работает
и без JS (паттерн `income_create`).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed
from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.expense_dialog import expense_dialog_context
from app.finance.services.expense_form import parse_expense_form
from app.finance.services.expense_writer import create_expense
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.post("/tutor/expenses", response_class=HTMLResponse)
async def create_expense_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт расход; `tutor_id` — только из сессии."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = await request.form()
    data, errors = parse_expense_form(form)

    if not errors:
        _, errors = create_expense(db, tutor_id, data, tutor)

    if errors:
        return templates.TemplateResponse(
            request,
            "finance/_expense_dialog.html",
            expense_dialog_context(tutor, data=data, errors=errors),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url="/tutor/finance", status_code=303)
    return dialog_closed("expense-saved")
