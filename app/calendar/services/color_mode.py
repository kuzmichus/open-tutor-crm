"""Режимы раскраски карточек календаря (design.md D5).

Режим приходит query-параметром `?color=target|status` и применяется на
сервере: точки в шапке дня и акцент карточки считаются одним правилом,
поэтому не могут разойтись. «По цели» — цвет закреплён за учеником или
группой (`students.color`/`groups.color`), «По статусу» — фиксированные
цвета запланированного, просроченного и проведённого урока.
"""

# Режимы раскраски: цель урока или его статус.
TARGET = "target"
STATUS = "status"
COLOR_MODES: tuple[str, ...] = (TARGET, STATUS)
DEFAULT_COLOR_MODE = TARGET

# Статусные цвета фиксированы (design.md D5): запланирован — синий,
# просрочен — красный, проведён — серый. Отменённый — тоже серый, но
# карточка дополнительно приглушается и зачёркивается; перенесённый —
# янтарный, чтобы отличался от обычного запланированного.
STATUS_PLANNED_COLOR = "#3b82f6"
STATUS_OVERDUE_COLOR = "#ef4444"
STATUS_COMPLETED_COLOR = "#9ca3af"
STATUS_CANCELLED_COLOR = "#9ca3af"
STATUS_RESCHEDULED_COLOR = "#f59e0b"


def parse_color_mode(raw: str | None) -> str:
    """`?color=` → режим раскраски; пустое/неизвестное значение — по цели.

    Некорректный параметр не ошибка: календарь рендерится в режиме по
    умолчанию (тот же приём, что у `?start=`).
    """
    return raw if raw in COLOR_MODES else DEFAULT_COLOR_MODE


def status_color(
    *, is_completed: bool, is_overdue: bool, status: str = ""
) -> str:
    """Акцентный цвет урока в режиме «По статусу».

    Проведённый урок важнее просрочки: у проведённого время тоже прошло,
    но он выполнен, а не пропущен. Отменённый и перенесённый уроки не
    «просрочены»: их время прошло по плану, но занятие не состоялось.
    """
    if is_completed:
        return STATUS_COMPLETED_COLOR
    if status == "cancelled":
        return STATUS_CANCELLED_COLOR
    if status == "rescheduled":
        return STATUS_RESCHEDULED_COLOR
    if is_overdue:
        return STATUS_OVERDUE_COLOR
    return STATUS_PLANNED_COLOR
