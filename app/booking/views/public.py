"""Публичная страница записи и приём заявки (design.md D7, D8, D12).

Два маршрута без сессии — единственная публичная поверхность проекта:

- `GET /s/<tutor_id>?start=YYYY-MM-DD&slot=<id>` — сетка недели и форма;
- `POST /s/<tutor_id>/book` — заявка на выбранное окно.

**Доступ.** `tutor_id` берётся из адреса, а не из сессии (сессии здесь нет
по определению). Неизвестный идентификатор даёт обычную 404-страницу
проекта, а не отдельный шаблон: существование чужого аккаунта не
раскрывается (тот же принцип, что 404 вместо 403 в `get_owned_*`).

**Что показывается.** Дата, время и состояние публичных окон недели:
свободное — выбор, занятое — «Занято» без указания, кем занято. Ни имён
учеников, ни заметок, ни контактов (design D1).

**Выбор окна** приходит параметром `slot` в адресе: сервер засчитывает его,
только если окно реально есть в отрисованной сетке и свободно (design D2).
Кривой или чужой `slot` молча игнорируется — ученик видит сетку без формы,
а не ошибку.

**Заявка.** Форма шлёт `slot_id`, имя, контакт и комментарий. Окно
перечитывается из БД по id и проверяется заново: пока ученик заполнял
форму, педагог мог снять публичность, поставить урок или окно могло пройти.
Тогда бронь не создаётся, а страница показывает причину и сохранённые
значения.

**Лимит** (design D12) проверяется до создания брони и увеличивается после
успешной заявки: неудачная попытка (опечатка в имени) не съедает лимит.

Ответ на успешную заявку — экран «Заявка отправлена!» с выбранным временем
(design D3): сетку и форму после успеха показывать незачем, окно уже
занято ожидающей бронью.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.booking.services.availability import (
    public_week,
    selected_slot,
    unavailable_reason,
)
from app.booking.services.booking_form import (
    booking_form_values,
    parse_booking_form,
)
from app.booking.services.booking_writer import request_booking
from app.booking.services.public_presentation import (
    selected_summary,
    selected_time_label,
    utc_offset_label,
    week_range,
    weekday_name,
    day_number,
    zone_banner,
)
from app.booking.services.rate_limit import (
    RATE_LIMITED_MESSAGE,
    client_fingerprint,
    is_rate_limited,
    register_attempt,
)
from app.common.services.tutor_time import now_utc, today_local, tutor_zone_name
from app.database import get_db
from app.slot.models.slot import Slot
from app.slot.services.public_link import PUBLIC_PREFIX, week_from_start
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.unavailability.services.marks import coverage_for_week

router = APIRouter()

# Понятное сообщение вместо «окно не найдено»: ученик пришёл по ссылке, а
# не вводил адрес руками, поэтому причина должна быть человеческой.
SLOT_GONE_MESSAGE = "Это окно больше недоступно. Выберите другое время."

# Подтверждение после успешной заявки (спека public-booking).
SENT_TITLE = "Заявка отправлена!"
SENT_MESSAGE = "Ожидайте подтверждение от преподавателя."

def _tutor_or_none(db: Session, tutor_id: str) -> Tutor | None:
    """Репетитор по id из адреса; неизвестный id — None (вьюха отдаёт 404)."""
    return db.get(Tutor, tutor_id)

def _days_context(days) -> list[dict]:
    """Столбцы сетки для шаблона: подписи дня и карточки окон.

    Ссылка выбора собирается здесь, а не в шаблоне: адрес должен нести и
    понедельник недели, и id окна — после выбора страница остаётся на той
    же неделе (design D2).
    """
    return [
        {
            "date": day.day,
            "weekday": weekday_name(day.day),
            "day_number": day_number(day.day),
            "is_empty": day.is_empty,
            "slots": day.slots,
        }
        for day in days
    ]

def _page(
    request: Request,
    db: Session,
    tutor: Tutor,
    monday,
    *,
    now: datetime,
    slot_id: str | None = None,
    message: str = "",
    errors: list[str] | None = None,
    values: dict | None = None,
    success: bool = False,
    sent_label: str = "",
) -> HTMLResponse:
    """Страница записи: сетка недели, форма выбранного окна или экран успеха.

    Один сборщик контекста на GET и POST: после неудачной заявки страница
    выглядит так же, как до неё, плюс сообщение — ученик не теряет сетку и
    видит, что поправить.
    """
    coverage = coverage_for_week(db, tutor.id, monday)
    days = public_week(db, tutor.id, monday, tutor, now=now)
    selected = selected_slot(days, slot_id)
    zone_name = tutor_zone_name(tutor)

    return templates.TemplateResponse(
        request,
        "booking/public.html",
        {
            "booking_tutor": tutor,
            "booking_monday": monday,
            "booking_days": _days_context(days),
            "booking_selected": selected,
            "booking_selected_summary": (
                selected_summary(
                    selected.day, selected.start, selected.end
                )
                if selected
                else ""
            ),
            "booking_week_label": week_range(monday, monday + timedelta(days=6)),
            # Причина вместо сетки — только когда неделя целиком в
            # недоступности: иначе пустая сетка объясняется подписью
            # «нет мест» в каждом столбце (спека public-booking).
            "booking_unavailable": unavailable_reason(coverage, monday),
            "booking_zone_banner": zone_banner(
                zone_name, utc_offset_label(tutor)
            ),
            "booking_message": message,
            "booking_errors": errors or [],
            "booking_values": values
            or {"name": "", "contact": "", "comment": ""},
            "booking_success": success,
            "booking_sent_label": sent_label,
            # Ссылки на соседние недели: ученик может посмотреть дальше,
            # не возвращаясь в мессенджер за новой ссылкой. Выбор окна при
            # листании сбрасывается — оно к другой неделе не относится.
            "booking_prev": (
                f"{PUBLIC_PREFIX}/{tutor.id}?start="
                f"{(monday - timedelta(days=7)).isoformat()}"
            ),
            "booking_next": (
                f"{PUBLIC_PREFIX}/{tutor.id}?start="
                f"{(monday + timedelta(days=7)).isoformat()}"
            ),
            "booking_prev_label": week_range(
                monday - timedelta(days=7), monday - timedelta(days=1)
            ),
            "booking_next_label": week_range(
                monday + timedelta(days=7), monday + timedelta(days=13)
            ),
            "booking_action": f"{PUBLIC_PREFIX}/{tutor.id}/book",
            "booking_slot_url": f"{PUBLIC_PREFIX}/{tutor.id}",
            "booking_monday_iso": monday.isoformat(),
        },
    )

@router.get(f"{PUBLIC_PREFIX}/{{tutor_id}}", response_class=HTMLResponse)
def public_page(
    tutor_id: str,
    request: Request,
    start: str | None = None,
    slot: str | None = None,
    db: Session = Depends(get_db),
):
    """Публичная страница недели; входа не требует (спека public-booking)."""
    tutor = _tutor_or_none(db, tutor_id)
    if tutor is None:
        # Обычная 404 проекта: не раскрываем, существует ли такой аккаунт.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    monday = week_from_start(start, today_local(tutor))
    return _page(request, db, tutor, monday, now=now_utc(), slot_id=slot)

@router.post(f"{PUBLIC_PREFIX}/{{tutor_id}}/book", response_class=HTMLResponse)
def submit_booking(
    tutor_id: str,
    request: Request,
    name: str = Form(""),
    contact: str = Form(""),
    comment: str = Form(""),
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

    form = {"name": name, "contact": contact, "comment": comment}
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
            slot_id=slot_id,
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
            slot_id=slot.id,
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

    # Подпись выбранного времени считается до записи: после неё окно стало
    # занятым и в сетке его уже нет, а экран успеха обязан показать время.
    sent_label = selected_time_label(slot.starts_at, slot.duration_min, tutor)

    booking, errors = request_booking(db, slot, params, now=now)
    if errors:
        return _page(
            request,
            db,
            tutor,
            monday,
            now=now,
            slot_id=slot.id,
            errors=errors,
            values=booking_form_values(form),
        )

    return _page(
        request,
        db,
        tutor,
        monday,
        now=now,
        success=True,
        message=SENT_MESSAGE,
        sent_label=sent_label,
    )
