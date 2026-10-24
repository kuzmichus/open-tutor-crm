"""Недельный календарь репетитора: реальные уроки недели из БД."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.calendar.services.color_mode import parse_color_mode
from app.calendar.services.week import week_start
from app.calendar.services.presentation import build_calendar_context
from app.calendar.services.week_days import build_week_days
from app.common.access import require_tutor_id
from app.common.services.tutor_time import (
    now_local,
    today_local,
    tutor_zone_name,
)
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

    «Сегодня» и «сейчас» считаются в зоне педагога (design D7): неделя
    открывается по его календарю, а не по календарю сервера.
    """
    tutor = db.get(Tutor, tutor_id)

    try:
        monday = week_start(start) if start else week_start(today_local(tutor))
    except ValueError:
        monday = week_start(today_local(tutor))

    context = build_calendar_context(
        build_week_days(db, tutor_id, monday, tutor),
        now=now_local(tutor),
        tutor=tutor,
        color_mode=parse_color_mode(color),
    )
    context["timezone_label"] = tutor_zone_name(tutor)
    # Локальный момент для клиента: `calendar.js` берёт «сегодня» и
    # предзаполнение отсюда, а не от часов устройства (design D7).
    context["now_iso"] = now_local(tutor).isoformat()
    if _is_htmx(request):
        return templates.TemplateResponse(request, "calendar/_area.html", context)
    return templates.TemplateResponse(request, "calendar/index.html", context)
