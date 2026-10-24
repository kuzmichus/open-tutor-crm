"""Создание окна: диалог (GET) и сохранение (POST).

GET `/tutor/slots/new` отдаёт `slot/_dialog.html` в контейнер `#modal`:
точка входа — пункт «Добавить слот» меню «⋯» календаря (спека calendar,
«Меню "⋯" открывает создание окна»). `?date=`/`?time=` приходят из
календаря и предзаполняют режим «Одно окно»; кривые значения просто
игнорируются — диалог открывается с пустыми полями.

POST принимает форму одного окна: успех — пустое тело и событие
`slot-saved`, по которому неделя перерисовывается с сервера. Без JS
(нет `HX-Request`) ответ — 303 на календарь: форма работает и без htmx.

При ошибке возвращается сам диалог с сообщением и присланными
значениями: введённое пользователем не теряется (паттерн
`lesson/views/create.py`).
"""

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import dialog_closed
from app.database import get_db
from app.slot.services.access import require_tutor_id
from app.slot.services.dialog_context import dialog_context
from app.slot.services.slot_form import parse_slot_form, slot_form_values
from app.slot.services.slot_writer import create_slot
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

SLOTS_URL = "/tutor/slots"
CALENDAR_URL = "/tutor/calendar"


def _prefill(date_value: str | None, time_value: str | None) -> dict | None:
    """Дата и время из календаря как `starts_at`; кривые значения — None.

    Оба параметра обязательны: половина момента не даёт предзаполнения,
    а `?date=` без `?time=` — это скорее ссылка на день, чем на окно.
    """
    if not date_value or not time_value:
        return None
    try:
        day = date.fromisoformat(date_value)
        moment = time.fromisoformat(time_value)
    except ValueError:
        return None
    return {"starts_at": datetime.combine(day, moment)}


def _form_data(form) -> dict:
    """Присланные значения формы в виде, который понимает `dialog_context`."""
    return slot_form_values(form)


@router.get(f"{SLOTS_URL}/new", response_class=HTMLResponse)
def new_slot_dialog(
    request: Request,
    date: str | None = None,
    time: str | None = None,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Диалог создания окна в режиме «Одно окно»."""
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "slot/_dialog.html",
        dialog_context(db, tutor, data=_prefill(date, time)),
    )


@router.post(SLOTS_URL, response_class=HTMLResponse)
async def create_slot_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт одно окно; `tutor_id` берётся только из сессии."""
    tutor = db.get(Tutor, tutor_id)
    form = await request.form()
    params, errors = parse_slot_form(form)

    if not errors:
        _, errors = create_slot(db, tutor, params)

    if errors:
        return templates.TemplateResponse(
            request,
            "slot/_dialog.html",
            dialog_context(db, tutor, data=_form_data(form), errors=errors),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=CALENDAR_URL, status_code=303)
    # Диалог закрывает подписка на `slot-saved`, а неделю она же и
    # перерисовывает (спека calendar, «Сохранение окна обновляет неделю»).
    # `HX-Reswap: none` — чтобы htmx не подменял пустым телом уже закрытый
    # и отсоединённый диалог.
    return dialog_closed()
