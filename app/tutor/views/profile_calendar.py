"""Сохранение настроек календаря (вкладка «Календарь», POST).

Значения распределяются по двум местам хранения: часовой пояс живёт в
карточке репетитора (вся система показа времени читает его оттуда),
остальное — в настройках.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.calendar_form import parse_calendar_form
from app.tutor.services.profile_page import profile_page_context
from app.tutor.services.settings import save_settings

router = APIRouter()


@router.post("/tutor/profile/calendar", response_class=HTMLResponse)
def profile_calendar(
    request: Request,
    timezone: str = Form(""),
    quarter1_end: str = Form(""),
    quarter2_end: str = Form(""),
    quarter3_end: str = Form(""),
    quarter4_end: str = Form(""),
    default_lesson_duration: str = Form(""),
    default_lesson_price: str = Form(""),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет часовой пояс, учебный год и уроки по умолчанию."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = {
        "timezone": timezone,
        "quarter1_end": quarter1_end,
        "quarter2_end": quarter2_end,
        "quarter3_end": quarter3_end,
        "quarter4_end": quarter4_end,
        "default_lesson_duration": default_lesson_duration,
        "default_lesson_price": default_lesson_price,
    }
    values, errors = parse_calendar_form(form)
    if errors:
        context = profile_page_context(
            db, tutor, tab="calendar", errors=errors, form=form,
        )
        return templates.TemplateResponse(request, "tutor/profile.html", context)

    tutor.timezone = values.pop("timezone")
    save_settings(db, tutor_id, values)

    return RedirectResponse(url="/tutor/profile?tab=calendar&saved=1", status_code=303)
