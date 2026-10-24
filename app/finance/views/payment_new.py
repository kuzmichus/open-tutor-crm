"""Диалог нового платежа (GET, design D11).

Открывается из вкладки «Платежи» карточки ученика в контейнер
`#modal-payment` — второй слой модалок (design D10): форма карточки со
своими несохранёнными полями остаётся нетронутой.

Ученик берётся из пути, а не из формы (design D11): диалог открыт из
карточки конкретного ученика, перенос платежа другому ученику — отдельный
сценарий, которого в требованиях нет. Чужой ученик и несуществующий
неразличимы: 404, а не 403.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import get_owned_student, require_tutor_id
from app.finance.services.payment_dialog import payment_dialog_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get(
    "/tutor/students/{student_id}/payments/new",
    response_class=HTMLResponse,
)
def new_payment_dialog(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма платежа; чужой ученик — 404."""
    student = get_owned_student(db, student_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "finance/_payment_dialog.html",
        payment_dialog_context(student, tutor),
    )
