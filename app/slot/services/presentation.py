"""Отображение окна: подписи состояний, причин пропуска и интервалов.

Чистые функции без БД и HTTP (как `app/lesson/services/presentation.py`):
принимают значения модели и карточку педагога, возвращают строки для
шаблона. Шаблон не форматирует бизнес-данные сам (правило AGENTS.md).

Подписи состояний (спека slot-management, «Занятость окна выводится
пересечением»): «Свободно», «Ожидает подтверждения», «Занято записью»,
«Занято уроком», «Время прошло». Подписи причин пропуска пачки — отдельный
словарь: пользователь видит, почему окно не создано, а не машинный код.
"""

from datetime import date, datetime, timedelta

from app.common.services.tutor_time import to_local
from app.slot.services.busy import (
    SLOT_BOOKED,
    SLOT_FREE,
    SLOT_LESSON,
    SLOT_PAST,
    SLOT_PENDING,
)
from app.slot.services.batch import (
    SKIP_BUSY_LESSON,
    SKIP_BUSY_SLOT,
    SKIP_PAST,
    SKIP_UNAVAILABLE_DAY,
)

# Подписи состояний окна в сетке календаря и в диалоге.
SLOT_STATE_LABELS = {
    SLOT_FREE: "Свободно",
    SLOT_PENDING: "Ожидает подтверждения",
    SLOT_BOOKED: "Занято записью",
    SLOT_LESSON: "Занято уроком",
    SLOT_PAST: "Время прошло",
}

# Подписи причин пропуска в отчёте пачки.
SKIP_REASON_LABELS = {
    SKIP_BUSY_LESSON: "Занято уроком",
    SKIP_BUSY_SLOT: "Занято другим окном",
    SKIP_UNAVAILABLE_DAY: "День отмечен как недоступный",
    SKIP_PAST: "Время прошло",
}

# Состояния, при которых карточка приглушается: время ушло или место занято.
MUTED_SLOT_STATES = (SLOT_BOOKED, SLOT_LESSON, SLOT_PAST)

_DASH = "—"  # прочерк: нет значения


def state_label(state: str) -> str:
    """Подпись состояния окна; неизвестное значение — как есть."""
    return SLOT_STATE_LABELS.get(state, state)


def skip_reason_label(reason: str) -> str:
    """Подпись причины пропуска окна в отчёте пачки."""
    return SKIP_REASON_LABELS.get(reason, reason)


def is_muted(state: str) -> bool:
    """Приглушается ли карточка окна в этом состоянии (спека calendar)."""
    return state in MUTED_SLOT_STATES


def format_span(starts_at: datetime, duration_min: int, tutor) -> str:
    """Интервал окна в зоне педагога: «10:00 – 10:40».

    Начало переводится из UTC в зону педагога, окончание считается уже
    в локальном времени — так интервал через переход на летнее время
    остаётся верным (design D3).
    """
    if starts_at is None:
        return ""
    start = to_local(starts_at, tutor)
    end = start + timedelta(minutes=duration_min or 0)
    return f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')}"


def format_day(starts_at: datetime, tutor) -> str:
    """«12.10.2026» — день окна в зоне педагога."""
    if starts_at is None:
        return ""
    return to_local(starts_at, tutor).strftime("%d.%m.%Y")


def format_day_time(starts_at: datetime, tutor) -> str:
    """«12.10.2026, 10:00» — день и начало окна для отчёта и диалога."""
    if starts_at is None:
        return ""
    return to_local(starts_at, tutor).strftime("%d.%m.%Y, %H:%M")


def format_local_day(day: date) -> str:
    """«12.10.2026» для пропуска: дата уже локальная (из `SlotSkip`)."""
    if day is None:
        return _DASH
    return day.strftime("%d.%m.%Y")


def format_local_time(value) -> str:
    """«10:00» для пропуска: время уже локальное (из `SlotSkip`)."""
    if value is None:
        return ""
    return value.strftime("%H:%M")


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        slot_state_label=state_label,
        slot_skip_reason_label=skip_reason_label,
        slot_is_muted=is_muted,
        slot_span=format_span,
        slot_day=format_day,
        slot_day_time=format_day_time,
        slot_local_day=format_local_day,
        slot_local_time=format_local_time,
    )
