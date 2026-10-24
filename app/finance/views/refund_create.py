"""Оформление возврата по платежу (POST, design D11).

Ответы те же, что у платежа: ошибка — фрагмент диалога с присланными
значениями и доступной суммой, успех — `dialog_closed("payment-saved")`,
без `HX-Request` — 303 на страницу карточки ученика.

Правила возврата («только по оплаченному платежу», «не больше остатка»)
проверяет `refunds.create_refund`: они требуют истории возвратов по этому
платежу, которой у формы нет.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed
from app.database import get_db
from app.finance.services.access import get_owned_student, require_tutor_id
from app.finance.services.refund_dialog import refund_dialog_context
from app.finance.services.refund_form import parse_refund_form
from app.finance.services.refunds import create_refund
from app.finance.views.payment_edit import get_owned_payment
from app.templating import templates

router = APIRouter()


@router.post("/tutor/payments/{payment_id}/refund", response_class=HTMLResponse)
async def create_refund_view(
    payment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт возврат; `tutor_id` берётся только из сессии."""
    payment = get_owned_payment(db, payment_id, tutor_id)
    student = get_owned_student(db, payment.student_id, tutor_id)

    form = await request.form()
    data, errors = parse_refund_form(form)

    if not errors:
        _, errors = create_refund(db, payment, data)

    if errors:
        return templates.TemplateResponse(
            request,
            "finance/_refund_dialog.html",
            refund_dialog_context(db, payment, student, data=data, errors=errors),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=f"/tutor/students/{student.id}", status_code=303)
    return dialog_closed("payment-saved")
