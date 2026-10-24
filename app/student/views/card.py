"""Карточка ученика (страница) и модалка карточки для htmx."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.card_summary import card_summary_context
from app.student.services.access import get_owned_student, require_tutor_id
from app.student.services.page_context import page_context
from app.student.services.students import build_cards
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/students/{student_id}", response_class=HTMLResponse)
def student_card(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Полная страница карточки; чужой ученик — 404.

    Сводка счёта (`finance/_card_summary.html`) собирается здесь же: страница
    показывает баланс и последние операции вместо прежней заглушки (design
    D12). Данные счёта считает модуль `finance`, страница их только выводит.
    """
    student = get_owned_student(db, student_id, tutor_id)
    card = build_cards(db, [student])[0]

    return templates.TemplateResponse(
        request,
        "student/card.html",
        page_context(
            db,
            request,
            tutor_id,
            card=card,
            **card_summary_context(db, student, db.get(Tutor, tutor_id)),
        ),
    )
