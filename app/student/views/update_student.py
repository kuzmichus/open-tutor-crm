"""Сохранение карточки ученика: поля, контакты, плательщик, напоминания."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import get_owned_student, require_tutor_id
from app.student.services.form_context import form_context
from app.student.services.presentation import form_from_data
from app.student.services.student_form import (
    parse_contact_rows,
    parse_student_form,
    validate_contacts,
)
from app.student.services.student_writer import update_student
from app.student.services.list_metrics import attach_card_metrics
from app.student.services.students import build_cards
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import as_utc, utcnow

router = APIRouter()


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@router.post("/tutor/students/{student_id}", response_class=HTMLResponse)
async def update_student_view(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Полное сохранение карточки; `id` и `tutor_id` не меняются."""
    student = get_owned_student(db, student_id, tutor_id)

    form = await request.form()
    # Форма помнит, откуда её открыли: со страницы карточки сетки в DOM нет.
    from_card = form.get("from_card") == "1"
    data, errors = parse_student_form(form)
    rows = parse_contact_rows(form)
    errors = errors + validate_contacts(rows)

    if not errors:
        errors = update_student(db, student, tutor_id, data, rows)

    if errors:
        context = form_context(
            db,
            form_from_data(data),
            tutor_id=tutor_id,
            student=student,
            errors=errors,
            rows=rows,
            from_card=from_card,
        )
        return templates.TemplateResponse(request, "student/_form.html", context)

    if not _is_htmx(request):
        return RedirectResponse(url="/tutor/students", status_code=303)

    if from_card:
        # Со страницы карточки проще перезагрузить её целиком: поля, контакты
        # и плательщик меняются сразу в нескольких блоках.
        response = Response(status_code=200)
        response.headers["HX-Refresh"] = "true"
        return response

    card = attach_card_metrics(
        db, build_cards(db, [student])[0], now=as_utc(utcnow())
    )
    response = templates.TemplateResponse(
        request, "student/_card.html", {"card": card, "tutor": db.get(Tutor, tutor_id)}
    )
    # Карточка заменяет себя в сетке, модалка закрывается по событию.
    response.headers["HX-Retarget"] = f"#student-card-{student.id}"
    response.headers["HX-Reswap"] = "outerHTML"
    response.headers["HX-Trigger"] = "student-saved"
    return response
