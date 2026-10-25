"""Архивирование ученика и возврат из архива."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import get_owned_student, require_tutor_id
from app.student.services.list_metrics import attach_card_metrics
from app.student.services.students import build_cards
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import as_utc, utcnow

router = APIRouter()


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@router.post("/tutor/students/{student_id}/archive", response_class=HTMLResponse)
def archive_student(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Переводит в архив или возвращает из архива одним действием.

    Действие определяется текущим статусом: архивный ученик становится
    активным, любой другой — архивным. Данные и контакты не меняются.
    """
    student = get_owned_student(db, student_id, tutor_id)
    student.status = "active" if student.status == "archived" else "archived"
    db.commit()

    if not _is_htmx(request):
        return RedirectResponse(url="/tutor/students", status_code=303)

    card = attach_card_metrics(
        db, build_cards(db, [student])[0], now=as_utc(utcnow())
    )
    response = templates.TemplateResponse(
        request, "student/_card.html", {"card": card, "tutor": db.get(Tutor, tutor_id)}
    )
    response.headers["HX-Retarget"] = f"#student-card-{student.id}"
    response.headers["HX-Reswap"] = "outerHTML"
    response.headers["HX-Trigger"] = "student-saved"
    return response
