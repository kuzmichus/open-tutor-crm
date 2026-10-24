"""Счёт за период — диалог второго слоя (GET, design D13).

Период и тумблер «Учесть остатки на балансе» передаются query-параметрами
(`from`, `to`, `balance`): счёт не сохраняется, поэтому состояние живёт в
адресе, а не в БД. Форма внутри диалога — GET, она перезапрашивает этот же
маршрут и меняет только свой фрагмент.

Без `HX-Request` маршрут всё равно отвечает фрагментом (не страницей):
счёт открывается только из карточки ученика, и отдельного адреса-страницы
у него нет.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import get_owned_student, require_tutor_id
from app.finance.services.invoice import invoice_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

# Тумблер учёта баланса: включён по умолчанию. Значение `0` — явный отказ,
# отсутствие параметра при первом открытии — «учесть».
BALANCE_ON = "1"
BALANCE_OFF = "0"


@router.get(
    "/tutor/students/{student_id}/invoice",
    response_class=HTMLResponse,
)
def student_invoice(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Диалог счёта за период; чужой ученик — 404."""
    student = get_owned_student(db, student_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    params = request.query_params
    context = invoice_context(
        db,
        student,
        tutor,
        from_raw=params.get("from"),
        to_raw=params.get("to"),
        use_balance=params.get("balance", BALANCE_ON) != BALANCE_OFF,
    )
    return templates.TemplateResponse(
        request,
        "finance/_invoice_dialog.html",
        context,
    )
