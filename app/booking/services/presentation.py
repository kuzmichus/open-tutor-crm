"""Отображение брони: подписи статусов и даты в зоне педагога.

Чистые функции без БД и HTTP (как `app/slot/services/presentation.py`):
принимают значения модели и карточку педагога, возвращают строки для
шаблона. Шаблон не форматирует бизнес-данные сам (правило AGENTS.md).

Подписи статусов берутся из модели (`BOOKING_STATUS_LABELS` — один
источник истины для CHECK-ограничения, options и подписей, AGENTS.md,
п. 10), здесь добавляется только показ: чип `chip--<статус>` и даты.

Кортеж месяцев в родительном падеже — локальная копия (в проекте их уже
три: calendar, finance, tutor): «умное» переиспользование тянуло бы
зависимость домена брони на домен календаря ради семи строк.
"""

from datetime import datetime

from app.booking.models.booking import BOOKING_STATUS_LABELS, Booking
from app.common.services.tutor_time import to_local

# Родительный падеж для дат карточки и истории: «26 октября 2026».
MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def booking_status_label(status: str) -> str:
    """Подпись статуса брони; неизвестное значение — как есть."""
    return BOOKING_STATUS_LABELS.get(status or "", status or "")


def day_full(starts_at: datetime, tutor) -> str:
    """«26 октября 2026» — дата окна карточки в зоне педагога."""
    local = to_local(starts_at, tutor)
    return (
        f"{local.day} {MONTHS_GENITIVE[local.month - 1]} {local.year}"
    )


def day_time(starts_at: datetime, tutor) -> str:
    """«21 октября, 15:00» — дата и начало окна в строке истории."""
    local = to_local(starts_at, tutor)
    return f"{local.day} {MONTHS_GENITIVE[local.month - 1]}, {local.strftime('%H:%M')}"


def decided_day(booking: Booking, tutor) -> str:
    """«15.10.2026» — дата решения в истории; без решения — пусто.

    У подтверждающих/завершающих статусов момент решения есть; пустая
    строка вместо даты создания — осознанно: колонка называется датой
    решения, подставлять туда другое событие — обманывать.
    """
    if booking.decided_at is None:
        return ""
    return to_local(booking.decided_at, tutor).strftime("%d.%m.%Y")
