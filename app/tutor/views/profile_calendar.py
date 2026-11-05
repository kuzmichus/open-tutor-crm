"""Сохранение настроек календаря (вкладка «Календарь», POST).

Значения распределяются по двум местам хранения: часовой пояс живёт в
карточке репетитора (вся система показа времени читает его оттуда),
остальное — в настройках.

Смена часового пояса пересчитывает сохранённые моменты времени: настенное
время расписания — инвариант, поэтому уроки, окна для записи, сроки ДЗ и
даты списаний переезжают в новые UTC-значения вместе с зоной
(`tutor/services/timezone_shift.py`). Календарь после смены зоны выглядит
так же, как до неё; меняется только подпись зоны в панели.
"""

import logging
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.common.services.tutor_time import tutor_zone, tutor_zone_name
from app.database import get_db
from app.gcalendar.services import sync as google_sync
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.calendar_form import parse_calendar_form
from app.tutor.services.profile_page import profile_page_context
from app.tutor.services.settings import save_settings
from app.tutor.services.timezone_shift import shift_tutor_schedule

logger = logging.getLogger("tutor")

router = APIRouter()


@router.post("/tutor/profile/calendar", response_class=HTMLResponse)
def profile_calendar(
    request: Request,
    timezone: str = Form(""),
    quarter1_end: str = Form(""),
    quarter2_end: str = Form(""),
    quarter3_end: str = Form(""),
    quarter4_end: str = Form(""),
    workday_start: str = Form(""),
    workday_end: str = Form(""),
    default_lesson_duration: str = Form(""),
    default_lesson_price: str = Form(""),
    weekly_load_hours: str = Form(""),
    preparation_coefficient: str = Form(""),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет часовой пояс, учебный год, рабочее время, уроки, нагрузку и
    коэффициент подготовки."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = {
        "timezone": timezone,
        "quarter1_end": quarter1_end,
        "quarter2_end": quarter2_end,
        "quarter3_end": quarter3_end,
        "quarter4_end": quarter4_end,
        "workday_start": workday_start,
        "workday_end": workday_end,
        "default_lesson_duration": default_lesson_duration,
        "default_lesson_price": default_lesson_price,
        "weekly_load_hours": weekly_load_hours,
        "preparation_coefficient": preparation_coefficient,
    }
    values, errors = parse_calendar_form(form)
    if errors:
        context = profile_page_context(
            db, tutor, tab="calendar", errors=errors, form=form,
        )
        return templates.TemplateResponse(request, "tutor/profile.html", context)

    new_zone_name = values.pop("timezone")
    # Сравниваем по имени, а не по объекту зоны: у старой зоны может быть
    # fallback на системную (пустое/некорректное поле карточки), и тогда
    # объекты отличаются, хотя показанное время одно и то же.
    old_zone_name = tutor_zone_name(tutor)
    zone_changed = new_zone_name != old_zone_name
    if zone_changed:
        # Имя валидировано формой, поэтому `ZoneInfo` не бросит исключение.
        # Сдвиг без коммита: `save_settings` сохранит расписание и настройки
        # одной транзакцией — при ошибке не останется полусдвинутого календаря.
        shift_tutor_schedule(
            db,
            tutor_id,
            tutor_zone(tutor),
            ZoneInfo(new_zone_name),
        )

    tutor.timezone = new_zone_name
    save_settings(db, tutor_id, values)

    if zone_changed:
        # Google — best-effort после коммита: события уже расходятся с БД по
        # времени, но ошибка внешнего сервиса не должна отменять сохранение
        # профиля. Сверка cron догонит пропущенное.
        try:
            google_sync.resync_tutor_events(db, tutor)
        except Exception:  # noqa: BLE001 — внешний сервис не ломает сохранение
            logger.exception("Google Календарь: ресинк после смены зоны упал")

    return RedirectResponse(url="/tutor/profile?tab=calendar&saved=1", status_code=303)
