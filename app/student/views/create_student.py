"""Создание ученика: обработка формы и возврат карточки в сетку."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import require_tutor_id
from app.student.services.form_context import form_context
from app.student.services.presentation import form_from_data
from app.student.services.student_form import (
    parse_contact_rows,
    parse_student_form,
    validate_contacts,
)
from app.student.services.student_writer import create_student
from app.student.services.students import build_cards
from app.templating import templates

router = APIRouter()


def _is_htmx(request: Request) -> bool:
    """True, если запрос пришёл от htmx (не полная навигация браузера)."""
    return request.headers.get("HX-Request") == "true"


@router.post("/tutor/students", response_class=HTMLResponse)
async def create_student_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт ученика; `tutor_id` берётся только из сессии.

    `tutor_id`, переданный в форме, игнорируется: владелец всегда вошедший
    репетитор. Успех — карточка ученика для вставки в сетку, ошибка — та же
    форма с сообщением.
    """
    form = await request.form()
    data, errors = parse_student_form(form)
    rows = parse_contact_rows(form)
    errors = errors + validate_contacts(rows)

    if errors:
        context = form_context(
            db,
            form_from_data(data),
            tutor_id=tutor_id,
            errors=errors,
            rows=rows,
        )
        return templates.TemplateResponse(request, "student/_form.html", context)

    student, save_errors = create_student(db, tutor_id, data, rows)
    if save_errors:
        context = form_context(
            db,
            form_from_data(data),
            tutor_id=tutor_id,
            errors=save_errors,
            rows=rows,
        )
        return templates.TemplateResponse(request, "student/_form.html", context)

    if not _is_htmx(request):
        return RedirectResponse(url="/tutor/students", status_code=303)

    card = build_cards(db, [student])[0]
    response = templates.TemplateResponse(
        request, "student/_card.html", {"card": card}
    )
    # Карточка встаёт в начало сетки, модалка закрывается по событию.
    response.headers["HX-Retarget"] = "#students-grid"
    response.headers["HX-Reswap"] = "afterbegin"
    response.headers["HX-Trigger"] = "student-saved"
    return response
