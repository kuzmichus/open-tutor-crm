"""Публичная страница записи и приём заявки (design.md D7, D8, D12).

Два маршрута без сессии — единственная публичная поверхность проекта:

- `GET /s/<tutor_id>?start=YYYY-MM-DD` — свободные окна недели;
- `POST /s/<tutor_id>/book` — заявка на конкретное окно.

**Доступ.** `tutor_id` берётся из адреса, а не из сессии (сессии здесь нет
по определению). Неизвестный идентификатор даёт обычную 404-страницу
проекта, а не отдельный шаблон: существование чужого аккаунта не
раскрывается (тот же принцип, что 404 вместо 403 в `get_owned_*`).

**Что показывается.** Только дата, время и длительность свободных
публичных окон. Ни имён учеников, ни заметок, ни контактов — выборка
`availability.free_slots` отдаёт лишь окна, а занятые не попадают в неё
вовсе (design D8).

**Заявка.** Форма шлёт `slot_id`, имя и контакт. Окно перечитывается из
БД по id и проверяется заново: пока ученик заполнял форму, педагог мог
снять публичность, поставить урок или окно могло пройти. Тогда бронь не
создаётся, а страница показывает причину.

**Лимит** (design D12) проверяется до создания брони и увеличивается после
успешной заявки: неудачная попытка (опечатка в имени) не съедает лимит.

Ответ на успешную заявку — та же страница с подтверждением «заявка
отправлена и ждёт подтверждения педагога»: отдельной страницы «спасибо»
нет, ученик остаётся на знакомой странице со списком окон.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.booking.services.availability import (
    free_slots,
    slots_by_day,
    unavailable_reason,
)
from app.booking.services.booking_form import (
    booking_form_values,
    parse_booking_form,
)
from app.booking.services.booking_writer import request_booking
from app.booking.services.rate_limit import (
    RATE_LIMITED_MESSAGE,
    client_fingerprint,
    is_rate_limited,
    register_attempt,
)
from app.common.services.tutor_time import now_utc, today_local, tutor_zone_name
from app.database import get_db
from app.slot.models.slot import Slot
from app.slot.services.public_link import week_from_start
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.unavailability.services.marks import coverage_for_week

router = APIRouter()

PUBLIC_PREFIX = "/s"

# Понятное сообщение вместо «окно не найдено»: ученик пришёл по ссылке, а
# не вводил адрес руками, поэтому причина должна быть человеческой.
SLOT_GONE_MESSAGE = "Это окно больше недоступно. Выберите другое время."

# Подтверждение после успешной заявки (спека public-booking).
SENT_MESSAGE = (
    "Заявка отправлена. Она ждёт подтверждения педагога — "
    "он свяжется с вами по указанному контакту."
)

def _tutor_or_none(db: Session, tutor_id: str) -> Tutor | None:
    """Репетитор по id из адреса; неизвестный id — None (вьюха отдаёт 404)."""
    return db.get(Tutor, tutor_id)

def _page(
    request: Request,
    db: Session,
    tutor: Tutor,
    monday,
    *,
    now: datetime,
    message: str = "",
    errors: list[str] | None = None,
    values: dict | None = None,
) -> HTMLResponse:
    """Страница записи: окна недели, подпись пояса и состояние формы.

    Один сборщик контекста на GET и POST: после неудачной заявки страница
    выглядит так же, как до неё, плюс сообщение — ученик не теряет список
    окон и видит, что поправить.
    """
    coverage = coverage_for_week(db, tutor.id, monday)
    slots = free_slots(db, tutor.id, monday, tutor, now=now)

    return templates.TemplateResponse(
        request,
        "booking/public.html",
        {
            "booking_tutor": tutor,
            "booking_monday": monday,
            "booking_days": slots_by_day(slots),
            "booking_empty": not slots,
            # Причина вместо списка — только когда неделя целиком в
            # недоступности: иначе пустой список объясняется подписью
            # «свободных окон нет» (спека public-booking).
            "booking_unavailable": unavailable_reason(coverage, monday),
            "booking_timezone": tutor_zone_name(tutor),
            "booking_message": message,
            "booking_errors": errors or [],
            "booking_values": values or {"name": "", "contact": ""},
            # Ссылки на соседние недели: ученик может посмотреть дальше,
            # не возвращаясь в мессенджер за новой ссылкой.
            "booking_prev": (
                f"{PUBLIC_PREFIX}/{tutor.id}?start="
                f"{(monday - timedelta(days=7)).isoformat()}"
            ),
            "booking_next": (
                f"{PUBLIC_PREFIX}/{tutor.id}?start="
                f"{(monday + timedelta(days=7)).isoformat()}"
            ),
            "booking_action": f"{PUBLIC_PREFIX}/{tutor.id}/book",
        },
    )

@router.get(f"{PUBLIC_PREFIX}/{{tutor_id}}", response_class=HTMLResponse)
def public_page(
    tutor_id: str,
    request: Request,
    start: str | None = None,
    db: Session = Depends(get_db),
):
    """Публичная страница недели; входа не требует (спека public-booking)."""
    tutor = _tutor_or_none(db, tutor_id)
    if tutor is None:
        # Обычная 404 проекта: не раскрываем, существует ли такой аккаунт.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    monday = week_from_start(start, today_local(tutor))
    return _page(request, db, tutor, monday, now=now_utc())

@router.post(f"{PUBLIC_PREFIX}/{{tutor_id}}/book", response_class=HTMLResponse)
def submit_booking(
    tutor_id: str,
    request: Request,
    name: str = Form(""),
    contact: str = Form(""),
    slot_id: str = Form(""),
    start: str = Form(""),
    db: Session = Depends(get_db),
):
    """Принимает заявку на окно; при отказе показывает причину и форму.

    Поля собираются в словарь вручную: `booking_form` работает с
    отображением формы, а не с именованными аргументами FastAPI, и должен
    оставаться независимым от HTTP (как `slot_form`).
    """
    tutor = _tutor_or_none(db, tutor_id)
    if tutor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    form = {"name": name, "contact": contact}
    monday = week_from_start(start, today_local(tutor))
    now = now_utc()

    params, errors = parse_booking_form(form)
    if errors:
        return _page(
            request,
            db,
            tutor,
            monday,
            now=now,
            errors=errors,
            values=booking_form_values(form),
        )

    slot = db.get(Slot, slot_id) if slot_id else None
    if slot is None or slot.tutor_id != tutor.id:
        # Чужое окно и несуществующее неразличимы — как везде в проекте.
        return _page(
            request,
            db,
            tutor,
            monday,
            now=now,
            errors=[SLOT_GONE_MESSAGE],
            values=booking_form_values(form),
        )

    fingerprint = client_fingerprint(request)
    if is_rate_limited(db, slot.id, fingerprint, now=now):
        # Подробности проверки не раскрываются (design D12).
        return _page(
            request,
            db,
            tutor,
            monday,
            now=now,
            errors=[RATE_LIMITED_MESSAGE],
            values=booking_form_values(form),
        )

    # Попытка считается здесь, а не после успешной заявки: окно принимает
    # только одну активную бронь, поэтому «считать успешные» сделало бы
    # лимит недостижимым — после первой заявки окно занято, и счётчик
    # застыл бы на единице. Спам по одной ссылке отсекается именно числом
    # отправок, а не числом созданных броней.
    #
    # Ошибки разбора формы и неизвестное окно выше счётчик не трогают:
    # опечатка в имени не должна съедать лимит и мешать исправить форму.
    register_attempt(db, slot.id, fingerprint, now=now)

    booking, errors = request_booking(db, slot, params, now=now)
    if errors:
        return _page(
            request,
            db,
            tutor,
            monday,
            now=now,
            errors=errors,
            values=booking_form_values(form),
        )

    # После заявки окно занято ожидающей бронью и из списка исчезает —
    # страница перерисовывается уже без него, с подтверждением.
    return _page(request, db, tutor, monday, now=now, message=SENT_MESSAGE)
