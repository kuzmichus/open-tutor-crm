"""Отображение задачи: подписи этапа и приоритета, короткая дата срока.

Чистые функции без БД и HTTP (как `booking/services/presentation.py`):
принимают значения модели и дату «сегодня» в зоне педагога, возвращают
строки для шаблона. Шаблон бизнес-данные не форматирует (правило
AGENTS.md).

Подписи берутся из закрытых списков модели (`TASK_STAGE_LABELS`,
`TASK_PRIORITY_LABELS`) — один источник истины с CHECK-ограничениями,
здесь добавляется только формат даты.

Кортеж месяцев — локальная копия, как в booking: «умное»
переиспользование тянуло бы зависимость домена задач на домен брони
ради двенадцати строк.
"""

from datetime import date

from app.task.models.task import TASK_PRIORITY_LABELS, TASK_STAGE_LABELS

# Короткие месяцы для срока карточки: «26 окт.».
MONTHS_SHORT = (
    "янв.", "февр.", "мар.", "апр.", "мая", "июн.",
    "июл.", "авг.", "сент.", "окт.", "нояб.", "дек.",
)


def stage_label(stage: str) -> str:
    """Подпись этапа; неизвестное значение — как есть."""
    return TASK_STAGE_LABELS.get(stage or "", stage or "")


def priority_label(priority: str) -> str:
    """Подпись приоритета; неизвестное значение — как есть."""
    return TASK_PRIORITY_LABELS.get(priority or "", priority or "")


def due_label(due_date: date | None, today: date) -> str:
    """«26 окт.» — срок задачи; год добавляется только у другого года.

    Пустой срок — пустая строка: карточка не показывает «Без срока»
    отдельным чипом, отсутствие даты и так видно.
    """
    if due_date is None:
        return ""
    text = f"{due_date.day} {MONTHS_SHORT[due_date.month - 1]}"
    if due_date.year != today.year:
        text = f"{text} {due_date.year}"
    return text


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        task_stage_label=stage_label,
        task_priority_label=priority_label,
        task_due_label=due_label,
    )
