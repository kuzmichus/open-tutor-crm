"""Партиал списка учеников для htmx (поиск, фильтры, долг без перезагрузки)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import require_tutor_id
from app.student.services.list_metrics import attach_metrics, debt_summary
from app.student.services.students import build_cards, list_students, normalize_sort
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import as_utc, utcnow

router = APIRouter()


@router.get("/tutor/students/list", response_class=HTMLResponse)
def students_list_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Список (панель долга + сетка/таблица) с учётом query-фильтров."""
    tutor = db.get(Tutor, tutor_id)
    students = list_students(
        db,
        tutor_id,
        q=request.query_params.get("q", ""),
        status=request.query_params.get("status", ""),
        sort=request.query_params.get("sort", ""),
    )
    cards = attach_metrics(
        db,
        build_cards(db, students),
        now=as_utc(utcnow()),
    )

    debtors = request.query_params.get("debtors") == "1"
    if debtors:
        cards = [card for card in cards if card["balance"] < 0]

    return templates.TemplateResponse(
        request,
        "student/_list.html",
        {
            "cards": cards,
            "q": request.query_params.get("q", ""),
            "status": request.query_params.get("status", ""),
            "sort": normalize_sort(request.query_params.get("sort", "")),
            "debtors": debtors,
            "debt": debt_summary(cards),
            "tutor": tutor,
            "total": len(cards),
        },
    )
