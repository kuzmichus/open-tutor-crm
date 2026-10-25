"""Создание платежа со страницы финансов (POST, design D5–D6).

Отличается от `payment_create` источником ученика: там он приходит из
пути (диалог открыт из карточки), здесь — из формы, потому что репетитор
выбирает его сам. Правило пустого ученика: это ошибка валидации и
повторный диалог, а не 404 — «не выбрал» и «выбрал чужого» разные случаи.
Чужой или несуществующий ученик — 404: существование чужой записи
не раскрывается (правило изоляции student-finance).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed
from app.database import get_db
from app.finance.services.access import (
    LoginRequired,
    get_owned_student,
    require_tutor_id,
)
from app.finance.services.income_dialog import income_dialog_context
from app.finance.services.payment_form import parse_payment_form
from app.finance.services.payment_writer import create_payment
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

MISSING_STUDENT_MESSAGE = "Выберите ученика."


@router.post("/tutor/payments", response_class=HTMLResponse)
async def create_income_payment(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт платёж с учеником из формы; `tutor_id` — только из сессии."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = await request.form()
    data, errors = parse_payment_form(form)

    raw_student_id = form.get("student_id", "")
    student = None
    if isinstance(raw_student_id, str) and raw_student_id.strip():
        # Чужой и несуществующий ученик неразличимы — get_owned_student
        # отвечает 404 (правило изоляции).
        student = get_owned_student(db, raw_student_id.strip(), tutor_id)
    else:
        # Ученик не выбран — ошибка формы, а не «нет такого ученика».
        errors.insert(0, MISSING_STUDENT_MESSAGE)

    if not errors and student is not None:
        _, errors = create_payment(db, student.id, data, tutor)

    if errors:
        # Выбранный (свой) ученик сохраняется в повторной отрисовке:
        # ошибка в сумме не должна сбрасывать выбор.
        return templates.TemplateResponse(
            request,
            "finance/_payment_dialog.html",
            income_dialog_context(db, tutor, data=data, errors=errors,
                                  selected_student=student),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url="/tutor/finance", status_code=303)
    return dialog_closed("payment-saved")
