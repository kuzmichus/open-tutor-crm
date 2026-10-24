"""Диалог возврата по платежу (GET, design D11).

Открывается из строки платежа в панели во втором слое модалок
(`#modal-payment`, design D10). Диалог показывает сумму платежа и остаток
к возврату: то, что нельзя вычислить в форме, — историю возвратов по
этому платежу.

Чужой платёж, несуществующий и списание — 404 (правило `get_owned_payment`):
существование внутренней операции не раскрывается и не обсуждается
отдельным кодом.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import get_owned_student, require_tutor_id
from app.finance.services.refund_dialog import refund_dialog_context
from app.finance.views.payment_edit import get_owned_payment
from app.templating import templates

router = APIRouter()


@router.get(
    "/tutor/payments/{payment_id}/refund/new",
    response_class=HTMLResponse,
)
def new_refund_dialog(
    payment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Форма возврата; чужой или несуществующий платёж — 404."""
    payment = get_owned_payment(db, payment_id, tutor_id)
    student = get_owned_student(db, payment.student_id, tutor_id)
    return templates.TemplateResponse(
        request,
        "finance/_refund_dialog.html",
        refund_dialog_context(db, payment, student),
    )
