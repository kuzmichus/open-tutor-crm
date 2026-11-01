"""Контекст страницы настроек репетитора (`/tutor/profile`).

Один строитель контекста на GET и на ре-рендер с ошибками: шаблон
всегда читает значения полей из `form`, а строитель либо собирает их
из карточки и настроек (GET), либо берёт присланные (ошибка формы).
"""

from sqlalchemy.orm import Session

from app.common.services.timezones import timezone_options_json
from app.gcalendar.services.presentation import google_calendar_context
from app.messenger.services.binding import channels_block_context
from app.tutor.models.tutor import Tutor
from app.tutor.models.tutor_settings import REMINDER_OFFSETS, REMINDER_OFFSET_LABELS
from app.tutor.services.settings import get_settings

# Вкладки страницы: ключ в URL → подпись таба. Порядок — порядок табов.
TABS = (
    ("profile", "Профиль"),
    ("security", "Безопасность"),
    ("notifications", "Уведомления"),
    ("calendar", "Календарь"),
)

TAB_KEYS = tuple(key for key, _label in TABS)

# Каждая форма знает свой POST-адрес: шаблону не нужно строить пути.
TAB_ACTIONS = {
    "profile": "/tutor/profile/save",
    "security": "/tutor/profile/security",
    "notifications": "/tutor/profile/notifications",
    "calendar": "/tutor/profile/calendar",
}

# Опции селектов рабочего времени: целые часы суток «00:00»…«23:00»
# (дизайн D2 — select вместо time-input не даёт ввести минуты вовсе).
WORKDAY_HOUR_OPTIONS = tuple(f"{hour:02d}:00" for hour in range(24))


def normalize_tab(raw: str | None) -> str:
    """Ключ вкладки из query-параметра; неизвестное значение — «Профиль»."""
    return raw if raw in TAB_KEYS else "profile"


def _form_defaults(tutor: Tutor, settings, tab: str) -> dict:
    """Значения полей активной вкладки из текущего состояния карточки."""
    if tab == "profile":
        # Ставка приходит из Numeric(10, 2) как Decimal('2000.00'): для
        # поля формы лишние нули обрезаем — пользователь ввёл «2000».
        hourly_rate = tutor.hourly_rate
        rate_text = "" if hourly_rate is None else format(hourly_rate, "f").rstrip("0").rstrip(".")
        return {
            "name": tutor.name,
            "phone": tutor.phone or "",
            "about": tutor.about or "",
            "hourly_rate": rate_text,
            "experience": tutor.experience or "",
        }
    if tab == "security":
        return {"email": tutor.email, "new_password": "", "new_password_confirm": ""}
    if tab == "notifications":
        return {
            "notify_lesson_reminder": settings.notify_lesson_reminder,
            "notify_lesson_confirmation": settings.notify_lesson_confirmation,
            "notify_daily_digest": settings.notify_daily_digest,
            "notify_cancellation": settings.notify_cancellation,
            "notify_homework": settings.notify_homework,
            "notify_debtors_weekly": settings.notify_debtors_weekly,
            "notify_low_balance": settings.notify_low_balance,
            "notify_insufficient_funds": settings.notify_insufficient_funds,
            "notify_birthday": settings.notify_birthday,
            "reminder_offsets": list(settings.reminder_offsets or []),
            "digest_time": settings.digest_time,
            "low_balance_threshold": str(settings.low_balance_threshold),
        }
    # calendar
    return {
        "timezone": tutor.timezone or "",
        "quarter1_end": settings.quarter1_end,
        "quarter2_end": settings.quarter2_end,
        "quarter3_end": settings.quarter3_end,
        "quarter4_end": settings.quarter4_end,
        "workday_start": settings.workday_start,
        "workday_end": settings.workday_end,
        "default_lesson_duration": str(settings.default_lesson_duration),
        "default_lesson_price": (
            "" if settings.default_lesson_price is None
            else str(settings.default_lesson_price)
        ),
    }


def profile_page_context(
    db: Session,
    tutor: Tutor,
    tab: str,
    saved: bool = False,
    errors: list[str] | None = None,
    form: dict | None = None,
    channels_block: dict | None = None,
    google_calendar: dict | None = None,
    google_error: str = "",
) -> dict:
    """Контекст шаблона настроек: вкладки, карточка, настройки и форма."""
    settings = get_settings(db, tutor.id)
    tab = normalize_tab(tab)
    context = {
        "active_page": "settings",
        "user_name": tutor.name,
        "user_role": "Владелец",
        "tutor": tutor,
        "settings": settings,
        "tab": tab,
        "tabs": TABS,
        "action": TAB_ACTIONS[tab],
        "saved": saved,
        "errors": errors or [],
        "form": form if form is not None else _form_defaults(tutor, settings, tab),
        "timezone_options_json": timezone_options_json(),
        "reminder_offsets": REMINDER_OFFSETS,
        "reminder_offset_labels": REMINDER_OFFSET_LABELS,
        "workday_hour_options": WORKDAY_HOUR_OPTIONS,
    }
    if tab == "notifications":
        # Блок каналов рендерится сетенезависимо из параметров; готовый
        # словарь передают действия блока (их ошибки тоже внутри блока).
        if channels_block is None:
            channels_block = channels_block_context(db, tutor.id)
        context["channels_block"] = channels_block
    elif tab == "calendar":
        # Блок Google Календаря живёт вне формы настроек: у него свои
        # GET/POST-действия, а вложенные формы недопустимы.
        context["google_calendar"] = (
            google_calendar if google_calendar is not None
            else google_calendar_context(db, tutor.id, error=google_error)
        )
    return context
