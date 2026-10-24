"""Контекст диалога окна: значения формы, состояние и доступные действия.

Диалог один на создание и правку (`slot/_dialog.html`): `slot=None` —
создание, иначе правка. Два режима — «Одно окно» и «Несколько дней» —
дают два независимых набора значений, поэтому ключи контекста плоские:
шаблон читает `slot_form.*` и не знает, какой режим сейчас активен.

Состояние окна считается тем же сервисом, что и в календаре
(`busy.slot_states`), — диалог не заводит второй способ понять «занято».
По состоянию решается, какие действия показывать: «Записать ученика»
только у свободного окна, «Удалить» — только без активной брони.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.booking.services.panel import booking_panel
from app.common.services.tutor_time import now_local, now_utc, to_local
from app.lesson.models.lesson import LESSON_DURATIONS
from app.slot.models.slot import Slot
from app.slot.services.busy import SLOT_FREE, slot_states
from app.slot.services.slot_form import MAX_GAP_MIN, WEEKDAY_LABELS
from app.slot.services.slot_writer import has_active_booking

# Значения пачки по умолчанию: рабочий интервал из примера спеки
# (10:00–18:00, 40 минут, перерыв 15) и будни.
DEFAULT_DAY_START = time(10, 0)
DEFAULT_DAY_END = time(18, 0)
DEFAULT_DURATION_MIN = 40
DEFAULT_GAP_MIN = 15
DEFAULT_WEEKDAYS = (0, 1, 2, 3, 4)
DEFAULT_BATCH_DAYS = 28


def _single_values(slot: Slot | None, data: dict | None, tutor) -> dict:
    """Значения формы одного окна: присланные важнее сохранённых."""
    duration = DEFAULT_DURATION_MIN
    is_public = True
    day = ""
    start = ""
    if slot is not None:
        local = to_local(slot.starts_at, tutor)
        day = local.date().isoformat()
        start = local.strftime("%H:%M")
        duration = slot.duration_min
        is_public = slot.is_public
    if data is not None:
        starts_at = data.get("starts_at")
        if isinstance(starts_at, datetime):
            day = starts_at.date().isoformat()
            start = starts_at.strftime("%H:%M")
        duration = data.get("duration_min") or duration
        is_public = bool(data.get("is_public", is_public))
    return {
        "date": day,
        "time": start,
        "duration_min": duration,
        "is_public": is_public,
    }


def _batch_values(slot: Slot | None, data: dict | None, tutor) -> dict:
    """Значения формы пачки; по умолчанию — четыре недели с сегодняшнего дня."""
    today = now_local(tutor).date()
    values = {
        "date_from": today,
        "date_to": today + timedelta(days=DEFAULT_BATCH_DAYS - 1),
        "weekdays": DEFAULT_WEEKDAYS,
        "day_start": DEFAULT_DAY_START,
        "day_end": DEFAULT_DAY_END,
        "duration_min": DEFAULT_DURATION_MIN,
        "gap_min": DEFAULT_GAP_MIN,
        "is_public": True,
    }
    if data is not None:
        for key in ("date_from", "date_to", "day_start", "day_end", "duration_min", "gap_min"):
            if data.get(key) is not None:
                values[key] = data[key]
        if data.get("weekdays"):
            values["weekdays"] = tuple(data["weekdays"])
        values["is_public"] = bool(data.get("is_public", values["is_public"]))
    return values


def _input_date(value) -> str:
    """Значение для `input[type=date]`: «YYYY-MM-DD»."""
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")


def _input_time(value) -> str:
    """Значение для `input[type=time]`: «HH:MM»."""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value or "")


def _form_values(values: dict) -> dict:
    """Значения пачки в виде, пригодном для полей формы."""
    return {
        "date_from": _input_date(values["date_from"]),
        "date_to": _input_date(values["date_to"]),
        "weekdays": tuple(values["weekdays"]),
        "day_start": _input_time(values["day_start"]),
        "day_end": _input_time(values["day_end"]),
        "duration_min": values["duration_min"],
        "gap_min": values["gap_min"],
        "is_public": values["is_public"],
    }


def dialog_context(
    db: Session,
    tutor,
    *,
    slot: Slot | None = None,
    data: dict | None = None,
    errors: list[str] | None = None,
    mode: str = "single",
    preview: dict | None = None,
) -> dict:
    """Контекст `slot/_dialog.html`.

    `data` — присланные значения при ошибке: форма показывает введённое
    пользователем, а не сброшенные поля (паттерн `lesson_form_context`).
    `preview` — готовый блок отчёта пачки (`preview_context`): предпросмотр
    или результат создания; `None` — блок пуст.
    """
    now = now_utc()
    state = ""
    if slot is not None:
        state = slot_states(db, slot.tutor_id, [slot], now).get(slot.id, SLOT_FREE)

    can_delete = slot is not None and not has_active_booking(db, slot)
    # Локальные значения окна для ссылки «Записать ученика» и подзаголовка:
    # ссылка ведёт в форму урока, которая принимает настенное время педагога
    # (`?starts_at=`), а не UTC (design D3).
    local = to_local(slot.starts_at, tutor) if slot is not None else None
    return {
        "slot": slot,
        "slot_mode": mode if slot is None else "single",
        "slot_errors": errors or [],
        "slot_single": _single_values(slot, data, tutor),
        "slot_batch": _form_values(_batch_values(slot, data, tutor)),
        "slot_durations": LESSON_DURATIONS,
        "slot_weekdays": tuple(enumerate(WEEKDAY_LABELS)),
        "slot_max_gap": MAX_GAP_MIN,
        "slot_state": state,
        # Блок брони: кто заявился и какие действия доступны. Логика
        # «что можно с бронью» — знание домена броней, поэтому живёт в
        # `booking/services/panel.py`, а не в шаблоне окна.
        **booking_panel(db, slot),
        "slot_can_delete": can_delete,
        "slot_can_book": slot is not None and state == SLOT_FREE,
        "slot_preview": preview,
        # Настенные значения окна для ссылок и подписей шаблона.
        "slot_day_label": (
            local.strftime("%d.%m.%Y, %H:%M") if local is not None else ""
        ),
        "slot_local_date": local.date().isoformat() if local is not None else "",
        "slot_local_time_value": local.strftime("%H:%M") if local is not None else "",
    }


def preview_context(plan, tutor, *, created: int | None = None) -> dict:
    """Блок отчёта пачки: число окон, времена одного дня и пропуски.

    `plan` — `BatchPlan` из `batch.plan()` / `batch.apply()`. Пока
    `created is None`, это предпросмотр («Будет создано окон»); после
    создания передаётся фактическое число созданных окон.
    """
    day_times: list[str] = []
    first_day = None
    for starts_at in plan.create:
        local = to_local(starts_at, tutor)
        if first_day is None:
            first_day = local.date()
        if local.date() != first_day:
            break
        day_times.append(local.strftime("%H:%M"))

    return {
        "result": created is not None,
        "create": len(plan.create),
        "created": created if created is not None else len(plan.create),
        "skips": plan.skip,
        "skip_count": len(plan.skip),
        "total": plan.total,
        "errors": list(plan.errors),
        "day": first_day,
        "day_times": day_times,
    }
