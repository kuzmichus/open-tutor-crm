"""Сохранение правки платежа (POST, design D11).

Ответы те же, что у создания: ошибка — фрагмент диалога с присланными
значениями, успех — `dialog_closed("payment-saved")`, без `HX-Request` —
303 на страницу карточки ученика.

Отмена платежа с возвратом отклоняется в `payment_writer.update_payment`
(design D4): здесь ошибка просто показывается в диалоге, статус в БД
не меняется.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed
from app.common.responses import is_htmx
from app.database import get_db
from app.finance.services.access import get_owned_student, require_tutor_id
from app.finance.services.payment_dialog import payment_dialog_context
from app.finance.services.payment_form import parse_payment_form
from app.finance.services.payment_writer import update_payment
from app.finance.views.payment_edit import get_owned_payment
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.post("/tutor/payments/{payment_id}", response_class=HTMLResponse)
async def update_payment_view(
    payment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Применяет форму к платежу; чужой платёж отвечает как несуществующий."""
    payment = get_owned_payment(db, payment_id, tutor_id)
    student = get_owned_student(db, payment.student_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)

    form = await request.form()
    data, errors = parse_payment_form(form)

    if not errors:
        errors = update_payment(db, payment, data, tutor)

    if errors:
        return templates.TemplateResponse(
            request,
            "finance/_payment_dialog.html",
            payment_dialog_context(
                student, tutor, payment=payment, data=data, errors=errors
            ),
        )

    if not is_htmx(request):
        return RedirectResponse(url=f"/tutor/students/{student.id}", status_code=303)
    return dialog_closed("payment-saved")
