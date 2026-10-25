"""Сохранение настроек уведомлений (вкладка «Уведомления», POST)."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.notifications_form import parse_notifications_form
from app.tutor.services.profile_page import profile_page_context
from app.tutor.services.settings import save_settings

router = APIRouter()


@router.post("/tutor/profile/notifications", response_class=HTMLResponse)
def profile_notifications(
    request: Request,
    # Тогглы объявлены поимённо: чекбокс без галочки поле в форме не шлёт,
    # поэтому у каждого аргумента дефолт "" (нет поля — выключено).
    notify_lesson_reminder: str = Form(""),
    notify_lesson_confirmation: str = Form(""),
    notify_daily_digest: str = Form(""),
    notify_cancellation: str = Form(""),
    notify_homework: str = Form(""),
    notify_debtors_weekly: str = Form(""),
    notify_low_balance: str = Form(""),
    notify_insufficient_funds: str = Form(""),
    notify_birthday: str = Form(""),
    digest_time: str = Form(""),
    low_balance_threshold: str = Form(""),
    reminder_offsets: list[str] = Form([]),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет переключатели уведомлений вошедшего репетитора."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    form = {
        "notify_lesson_reminder": notify_lesson_reminder,
        "notify_lesson_confirmation": notify_lesson_confirmation,
        "notify_daily_digest": notify_daily_digest,
        "notify_cancellation": notify_cancellation,
        "notify_homework": notify_homework,
        "notify_debtors_weekly": notify_debtors_weekly,
        "notify_low_balance": notify_low_balance,
        "notify_insufficient_funds": notify_insufficient_funds,
        "notify_birthday": notify_birthday,
        "digest_time": digest_time,
        "low_balance_threshold": low_balance_threshold,
        # Чекбоксы шлют строки-минуты: для ре-рендера приводим к int,
        # чтобы проверка «отмечен ли» совпадала с дефолтами настроек.
        "reminder_offsets": [raw for raw in reminder_offsets if raw.isdigit()],
    }
    values, errors = parse_notifications_form(form)
    if errors:
        context = profile_page_context(
            db, tutor, tab="notifications", errors=errors, form=form,
        )
        return templates.TemplateResponse(request, "tutor/profile.html", context)

    save_settings(db, tutor_id, values)

    return RedirectResponse(
        url="/tutor/profile?tab=notifications&saved=1", status_code=303
    )
