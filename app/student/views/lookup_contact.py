"""Ленивый поиск существующего контакта при вводе телефона или email."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import require_tutor_id
from app.student.services.contact_lookup import lookup_contact
from app.templating import templates

router = APIRouter()

def _row_value(params, field: str, row_index: str) -> str:
    """Значение поля строки контакта: `contact_phone_0`, `contact_email_0`.

    Форма отправляет поля с индексом строки (`hx-include="closest .contact-row"`),
    поэтому телефон и email конкретной строки берутся по её номеру.
    """
    if row_index == "":
        return ""
    return params.get(f"contact_{field}_{row_index}", "")

@router.get("/tutor/students/contacts/lookup", response_class=HTMLResponse)
def lookup_contact_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """HTML-фрагмент подсказки; поиск только по контактам репетитора.

    Принимает либо готовые `phone`/`email`, либо `row_index` вместе с полями
    строки формы. `student_id` нужен, чтобы уже привязанный контакт не
    предлагался к повторной привязке.
    """
    params = request.query_params
    row_index = params.get("row_index", "")

    phone = params.get("phone", "") or _row_value(params, "phone", row_index)
    email = params.get("email", "") or _row_value(params, "email", row_index)
    student_id = params.get("student_id", "")

    found = lookup_contact(
        db, tutor_id, phone=phone, email=email, student_id=student_id
    )
    return templates.TemplateResponse(
        request,
        "student/_contact_suggestion.html",
        {"found": found},
    )
