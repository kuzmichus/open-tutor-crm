"""Запись окна: создание, перенос и удаление (design.md D2, D11).

Сервис не знает про FastAPI: на вход — `Session`, карточка педагога и
очищенные значения формы (`SlotParams`), на выход — строка или список
ошибок. Перевод настенного времени в UTC делает именно он: только здесь
есть карточка педагога, а форма отдаёт наивные значения (design D3).

Пересечение проверяется перед записью, а не только уникальностью
`(tutor_id, starts_at)`: индекс ловит точный дубль, но не наложение
14:00–14:40 и 14:10–14:50. Любое пересечение — занятость, в том числе
частичное (спека slot-management, «Пересечения пропускаются»).

Удаление блокируется активной бронью: бронь без окна не существует
(`ondelete="CASCADE"`), поэтому «удалить вместе с бронью» значило бы
молча потерять заявку человека. Сначала бронь отклоняется или отменяется
(design D11).
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.booking.models.booking import ACTIVE_BOOKING_STATUSES, Booking
from app.common.services.tutor_time import to_utc
from app.slot.models.slot import Slot
from app.slot.services.busy import (
    lesson_spans,
    lessons_for_range,
    overlaps,
    slot_spans,
    slots_for_range,
)
from app.slot.services.slot_form import SlotParams
from app.tutor.services.clock import as_utc

# Сообщения о конфликтах: пользователь должен видеть, чем именно занято
# время, — «урок» и «другое окно» лечатся по-разному.
BUSY_LESSON_MESSAGE = "На это время уже стоит урок."
BUSY_SLOT_MESSAGE = "На это время уже есть окно."
DUPLICATE_MESSAGE = "Окно на это время уже существует."
BUSY_BOOKING_MESSAGE = (
    "У окна есть активная бронь: сначала отклоните или отмените её."
)


def _window(params: SlotParams, tutor) -> tuple[datetime, datetime]:
    """Начало (aware UTC) и конец окна из значений формы."""
    starts_at = to_utc(params.starts_at, tutor)
    return starts_at, starts_at + timedelta(minutes=params.duration_min)


def _conflict_errors(
    db: Session,
    tutor_id: str,
    starts_at: datetime,
    finish: datetime,
    *,
    exclude_slot_id: str | None = None,
) -> list[str]:
    """Ошибки пересечения нового времени с уроками и окнами педагога.

    `exclude_slot_id` — само переносимое окно: без исключения оно
    конфликтовало бы с собой на прежнем времени.
    """
    lessons = lessons_for_range(db, tutor_id, starts_at, finish)
    if any(
        overlaps(starts_at, finish, lesson_start, lesson_end)
        for lesson_start, lesson_end in lesson_spans(lessons)
    ):
        return [BUSY_LESSON_MESSAGE]

    nearby = slots_for_range(db, tutor_id, starts_at, finish)
    busy_slots = [
        span
        for slot, span in zip(nearby, slot_spans(nearby), strict=True)
        if slot.id != exclude_slot_id
    ]
    if any(
        overlaps(starts_at, finish, slot_start, slot_end)
        for slot_start, slot_end in busy_slots
    ):
        return [BUSY_SLOT_MESSAGE]
    return []


def _active_bookings(db: Session, slot_id: str) -> int:
    """Сколько активных броней у окна (0 или 1 — частичный уникальный индекс)."""
    return db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.slot_id == slot_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
    ) or 0


def create_slot(
    db: Session, tutor, params: SlotParams
) -> tuple[Slot | None, list[str]]:
    """Создаёт одно окно; при конфликте ничего не пишет.

    Уникальность `(tutor_id, starts_at)` продублирована обработкой
    `IntegrityError`: между проверкой и вставкой могла пройти параллельная
    пачка, и вместо 500 пользователь получает понятное сообщение.
    """
    starts_at, finish = _window(params, tutor)
    errors = _conflict_errors(db, tutor.id, starts_at, finish)
    if errors:
        return None, errors

    slot = Slot(
        tutor_id=tutor.id,
        starts_at=starts_at,
        duration_min=params.duration_min,
        is_public=params.is_public,
    )
    db.add(slot)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None, [DUPLICATE_MESSAGE]
    return slot, []


def move_slot(db: Session, slot: Slot, tutor, params: SlotParams) -> list[str]:
    """Меняет начало, длительность и публичность окна (design D11).

    Бронь не трогается: она ссылается на окно по id и «едет» вместе с ним.
    Конфликт на новом времени — отказ, окно остаётся на прежнем месте.
    """
    starts_at, finish = _window(params, tutor)
    errors = _conflict_errors(
        db, slot.tutor_id, starts_at, finish, exclude_slot_id=slot.id
    )
    if errors:
        return errors

    slot.starts_at = starts_at
    slot.duration_min = params.duration_min
    slot.is_public = params.is_public
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return [DUPLICATE_MESSAGE]
    return []


def delete_slot(db: Session, slot: Slot) -> list[str]:
    """Удаляет окно без активной брони; уроки не трогает.

    Активная бронь (ожидающая или подтверждённая) блокирует удаление:
    бронь каскадна к окну, и «удалить» молча уничтожило бы заявку.
    """
    if _active_bookings(db, slot.id):
        return [BUSY_BOOKING_MESSAGE]

    db.delete(slot)
    db.commit()
    return []


def has_active_booking(db: Session, slot: Slot) -> bool:
    """Есть ли у окна активная бронь (для диалога: удаление недоступно)."""
    return bool(_active_bookings(db, slot.id))


def slot_is_past(slot: Slot, now: datetime) -> bool:
    """Закончилось ли окно к моменту `now` (aware UTC)."""
    return as_utc(slot.starts_at) + timedelta(
        minutes=slot.duration_min or 0
    ) <= as_utc(now)
