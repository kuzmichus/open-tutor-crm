"""Диалог правки платежа (GET, design D11).

Тот же шаблон, что и создание (`payment is None` → пустая форма): поля,
подписи и адрес сохранения собирает `payment_dialog_context`.

Править можно только платёж: списание и возврат — производные операции,
их правит урок или отдельный возврат. Строка другого вида в этом маршруте
отвечает 404 — как чужая, а не 400: существование внутренней операции
не раскрывается и не обсуждается отдельным кодом.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import (
    get_owned_operation,
    get_owned_student,
    require_tutor_id,
)
from app.finance.services.payment_dialog import payment_dialog_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


def get_owned_payment(db: Session, payment_id: str, tutor_id: str):
    """Платёж этого репетитора либо 404.

    `get_owned_operation` проверяет владельца одним `SELECT` с `JOIN`;
    вид операции проверяется здесь же, чтобы списание нельзя было открыть
    в форме платежа и сохранить с чужими полями.
    """
    payment = get_owned_operation(db, payment_id, tutor_id)
    if payment.kind != "payment":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return payment


@router.get("/tutor/payments/{payment_id}/edit", response_class=HTMLResponse)
def edit_payment_dialog(
    payment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Форма правки платежа; чужой или несуществующий — 404."""
    payment = get_owned_payment(db, payment_id, tutor_id)
    student = get_owned_student(db, payment.student_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "finance/_payment_dialog.html",
        payment_dialog_context(student, tutor, payment=payment),
    )
