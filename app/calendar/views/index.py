"""Недельный календарь репетитора: реальные уроки недели из БД."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.calendar.services.color_mode import parse_color_mode
from app.calendar.services.demo_schedule import week_start
from app.calendar.services.presentation import build_calendar_context
from app.calendar.services.week_days import build_week_days
from app.common.access import require_tutor_id
from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


def _is_htmx(request: Request) -> bool:
    """Запрос от htmx (листание недели) — отдаётся только область календаря."""
    return request.headers.get("HX-Request") == "true"


@router.get("/tutor/calendar", response_class=HTMLResponse)
def calendar(
    request: Request,
    start: str | None = None,
    color: str | None = None,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Календарь недели; `?start=` — любая дата недели, нормализуется к пн.

    Некорректное значение `start` не ошибка: календарь показывает текущую
    неделю (спека «Листание недель», design.md D4). `?color=target|status` —
    активный режим раскраски (design.md D5); неизвестное значение даёт
    режим по умолчанию. При заголовке `HX-Request` рендерится только
    область `#calendar-swap` — сетка подменяется без перезагрузки страницы.
    """
    try:
        monday = week_start(start) if start else week_start(date.today())
    except ValueError:
        monday = week_start(date.today())

    tutor = db.get(Tutor, tutor_id)
    context = build_calendar_context(
        build_week_days(db, tutor_id, monday),
        now=datetime.now(),
        tutor=tutor,
        color_mode=parse_color_mode(color),
    )
    if _is_htmx(request):
        return templates.TemplateResponse(request, "calendar/_area.html", context)
    return templates.TemplateResponse(request, "calendar/index.html", context)
