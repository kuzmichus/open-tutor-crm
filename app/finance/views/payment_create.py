"""Создание платежа (POST, design D11).

Ответы:

- ошибка валидации — тот же фрагмент диалога со списком ошибок и
  присланными значениями (`hx-target="#modal-payment"`,
  `hx-swap="outerHTML"`): форма карточки ученика не затрагивается;
- успех — пустое тело + `HX-Trigger: payment-saved` и `HX-Reswap: none`
  (`common/responses.dialog_closed`): диалог закрывает подписка на событие,
  а панель платежей перезапрашивает себя по тому же событию;
- без `HX-Request` — 303 на страницу карточки: форма работает и без JS.
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
from app.finance.services.payment_writer import create_payment
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.post("/tutor/students/{student_id}/payments", response_class=HTMLResponse)
async def create_payment_view(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт платёж; `tutor_id` берётся только из сессии.

    Зона педагога нужна дважды: по ней считается сегодняшняя дата формы и
    время операции (`payment_writer._occurred_at`), поэтому карточка
    репетитора читается один раз и передаётся дальше.
    """
    student = get_owned_student(db, student_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)

    form = await request.form()
    data, errors = parse_payment_form(form)

    if not errors:
        payment, errors = create_payment(db, student.id, data, tutor)

    if errors:
        return templates.TemplateResponse(
            request,
            "finance/_payment_dialog.html",
            payment_dialog_context(student, tutor, data=data, errors=errors),
        )

    if not is_htmx(request):
        return RedirectResponse(url=f"/tutor/students/{student.id}", status_code=303)
    return dialog_closed("payment-saved")
