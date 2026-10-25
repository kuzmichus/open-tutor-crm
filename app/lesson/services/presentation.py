"""Отображение урока: стоимость, цель, чип типа, оценка-звёзды.

Чистые функции без БД и HTTP (как `app/group/services/presentation.py`):
принимают значения модели и имена связанных записей, возвращают строки
для шаблона. Бизнес-правила живут в других сервисах модуля.

Правила (спека lesson-management):
- групповой урок стоит «—», у остальных — оплата ученика, а у
  проведённых — с суффиксом «(Оплачено)». Суффикс по-прежнему производная
  от статуса, а не от счёта ученика: источник истины по деньгам — вкладка
  «Платежи» (модуль `finance`), несоответствие зафиксировано как известное
  ограничение в README и в design change'а `student-finance`;
- цель: групповой — «Группа: <имя группы>», остальные — ученик;
- чип типа — русская подпись из `LESSON_TYPE_LABELS`;
- оценка для семьи — звёзды 1–5, без оценки — пустая строка.
"""

from datetime import datetime, timedelta

from app.common.services.tutor_time import to_local
from app.lesson.models.lesson import (
    LESSON_STATUS_LABELS,
    LESSON_TYPE_LABELS,
)

_DASH = "—"  # прочерк: нет значения

# Короткие названия месяцев в родительном падеже — для баннера напоминаний
# («24 окт., 23:30»). Третья копия в проекте (finance, tutor): цена
# разделения модулей, вынос в `app/common/` — отдельная задача.
_MONTHS_SHORT = (
    "янв.",
    "февр.",
    "мар.",
    "апр.",
    "мая",
    "июн.",
    "июл.",
    "авг.",
    "сент.",
    "окт.",
    "нояб.",
    "дек.",
)


def unmarked_notice_label(count: int) -> str:
    """«1 урок не отмечен» / «2 урока не отмечены» — подпись баннера.

    Русская плюрализация по стандартным правилам: 11–14 всегда «уроков»,
    иначе последняя цифра решает (1 — «урок», 2–4 — «урока», прочие —
    «уроков»); глагол согласуется: единственное число только при одном.
    """
    if count % 100 in (11, 12, 13, 14):
        plural, verb = "уроков", "не отмечены"
    elif count % 10 == 1:
        plural, verb = "урок", "не отмечен"
    elif count % 10 in (2, 3, 4):
        plural, verb = "урока", "не отмечены"
    else:
        plural, verb = "уроков", "не отмечены"
    return f"{count} {plural} {verb}"


def notice_when(value: datetime, tutor) -> str:
    """«24 окт., 23:30» — момент урока в баннере, зона педагога."""
    if value is None:
        return ""
    local = to_local(value, tutor)
    return f"{local.day} {_MONTHS_SHORT[local.month - 1]}, {local.strftime('%H:%M')}"


def _rubles(price: int) -> str:
    """«1 200 ₽»: разделитель разрядов — неразрывный пробел (как в group)."""
    return f"{price:,}".replace(",", "\u00a0") + "\u00a0₽"


def format_price(price: int | None, *, lesson_type: str, status: str) -> str:
    """Стоимость в колонке списка: «1 200 ₽ (Оплачено)», «1 200 ₽» или «—»."""
    if lesson_type == "group" or price is None:
        return _DASH
    label = _rubles(price)
    if status == "completed":
        label += " (Оплачено)"
    return label


def format_target(
    student_name: str | None, group_name: str | None, lesson_type: str
) -> str:
    """Цель урока: «Группа: <имя>» для группового, имя ученика для остальных."""
    if lesson_type == "group":
        return f"Группа: {group_name or _DASH}"
    return student_name or _DASH


def type_chip_label(lesson_type: str) -> str:
    """Подпись чипа типа: «Пробный»; неизвестное значение — как есть."""
    return LESSON_TYPE_LABELS.get(lesson_type, lesson_type)


def status_label(status: str) -> str:
    """Подпись статуса: «Запланирован» / «Проведён»."""
    return LESSON_STATUS_LABELS.get(status, status)


def format_rating(rating: int | None) -> str:
    """Оценка-звёзды: «★★★☆☆»; без оценки — пустая строка."""
    if rating is None or not isinstance(rating, int) or not 1 <= rating <= 5:
        return ""
    return "★" * rating + "☆" * (5 - rating)


def format_lesson_datetime(value: datetime, tutor) -> str:
    """«19.10.2026, 10:00» — колонка «Дата и время» списка уроков.

    Значение переводится из UTC в зону педагога; формат подписи не
    меняется (спека lesson-management, «Отображение времени урока»).
    """
    if value is None:
        return ""
    return to_local(value, tutor).strftime("%d.%m.%Y, %H:%M")


def format_lesson_date(value: datetime, tutor) -> str:
    """«17.05.2027» — дата занятия во вкладке «Занятия» группы.

    Время рядом показывает `lesson_time_span` (интервалом), поэтому дате
    он не нужен.
    """
    if value is None:
        return ""
    return to_local(value, tutor).strftime("%d.%m.%Y")


def homework_short_label(status: str | None) -> str:
    """«ДЗ: есть/нет» — индикатор домашнего задания в списке занятий группы.

    Записи ДЗ может не быть (создаётся лениво), а статус «Не задано» —
    формально существующая запись без задания; для списка это одно и то
    же «домашнего задания нет».
    """
    assigned = status is not None and status != "not_assigned"
    return "ДЗ: есть" if assigned else "ДЗ: нет"


def format_time_span(lesson, tutor) -> str:
    """Подзаголовок модалки редактирования: интервал «10:00–11:00».

    Начало и окончание считаются в зоне педагога (спека: «Интервал в
    модалке»), формат подписи не меняется.
    """
    if lesson is None or lesson.starts_at is None:
        return ""
    start = to_local(lesson.starts_at, tutor)
    end = start + timedelta(minutes=lesson.duration_min or 0)
    return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        lesson_price=format_price,
        lesson_target=format_target,
        lesson_type_chip=type_chip_label,
        lesson_status_label=status_label,
        lesson_rating=format_rating,
        lesson_datetime=format_lesson_datetime,
        lesson_date=format_lesson_date,
        lesson_time_span=format_time_span,
        homework_short_label=homework_short_label,
        unmarked_notice_label=unmarked_notice_label,
        notice_when=notice_when,
    )
