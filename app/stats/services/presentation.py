"""Отображение модуля статистики: проценты, «Занятий/нед», причины, метки дат.

Чистые функции без БД и HTTP (как в остальных модулях): сервисы возвращают
числа, шаблон вызывает отсюда готовые подписи. Десятичный разделитель —
запятая, деньги уже отформатированы глобальной `money()` из finance.
"""

from datetime import datetime

from app.common.services.tutor_time import to_local
from app.stats.services.new_and_trials import MIN_TRIALS_FOR_RATE
from app.stats.services.student_rows import ACTIVITY_LABELS

# Короткие названия месяцев в родительном падеже: ещё одна копия в проекте
# (finance, lesson, student, tutor) — цена разделения модулей, вынос в
# `app/common/` — отдельная задача.
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

# Подписи причин в раскрытии конверсии из пробного.
KEPT_REASON_LABELS = {
    "lesson": "есть занятие после пробного",
    "payment": "оплата после пробного",
}


def week_rate_label(count: int) -> str:
    """«Занятий/нед»: среднее за 4 недели — «0,5»; занятий нет — «0».

    Дробная часть всегда одна: «0,5» и «1,3» читаются как темп, а «1,25»
    создало бы ложную точность.
    """
    if count == 0:
        return "0"
    value = count / 4
    return f"{value:.1f}".replace(".", ",")


def percent_label(part: int, total: int) -> str:
    """Доля в процентах — «75%»; знаменатель нулевой — «—» (данных нет)."""
    if total == 0:
        return "—"
    return f"{round(part / total * 100)}%"


def conversion_label(trials: int, kept: int) -> str:
    """Конверсия из пробного: «—», «мало данных» или процент (design D7)."""
    if trials == 0:
        return "—"
    if trials < MIN_TRIALS_FOR_RATE:
        return "мало данных"
    return percent_label(kept, trials)


def kept_reason_label(reason: str | None) -> str:
    """Причина в списке пробных: «есть занятие после пробного» и т.п."""
    if reason is None:
        return "не остался: занятий и оплат после пробного нет"
    return KEPT_REASON_LABELS.get(reason, reason)


def activity_label(value: str | None) -> str:
    """Состояние активности в таблице: «Активен»/«Отвалился»/«Ушёл»; нет — «»."""
    return ACTIVITY_LABELS.get(value or "", "")


def _hours_number(hours: float) -> str:
    """Число часов «52,5» / «52»: целые — без дробной части.

    Часы считаются из минут, поэтому 60 минут — ровно «1», а не «1,0»:
    подпись «1 час» читается, «1,0 час» — нет.
    """
    if abs(hours - round(hours)) < 0.05:
        return str(round(hours))
    return f"{hours:.1f}".replace(".", ",")


def _hours_word(hours: float) -> str:
    """Склонение «час/часа/часов» для значения в часах.

    Дробное значение всегда «часа»: «0,5 часа», «1,5 часа» — так же, как
    «полтора часа»; правило «1 час / 2 часа / 5 часов» — только для целых.
    """
    if abs(hours - round(hours)) >= 0.05:
        return "часа"
    value = abs(round(hours))
    last_two = value % 100
    last = value % 10
    if 11 <= last_two <= 14:
        return "часов"
    if last == 1:
        return "час"
    if 2 <= last <= 4:
        return "часа"
    return "часов"


def hours_label(hours: float) -> str:
    """Астрономические часы коротко: «52,5 ч», «1,5 ч», «0 ч»."""
    return f"{_hours_number(hours)} ч"


def hours_phrase(hours: float) -> str:
    """Часы со склонением: «1,5 часа», «1 час», «2 часа», «5 часов»."""
    return f"{_hours_number(hours)} {_hours_word(hours)}"


def percent_or_dash(value: int | None) -> str:
    """Процент из готового числа: «80%»; значения нет — «—»."""
    if value is None:
        return "—"
    return f"{value}%"


def lesson_datetime_label(value: datetime | None, tutor) -> str:
    """«26.10.2026, 15:00» — момент занятия в зоне педагога; нет — «»."""
    if value is None:
        return ""
    local = to_local(value, tutor)
    return f"{local:%d.%m.%Y}, {local:%H:%M}"


def day_label(value: datetime | None, tutor) -> str:
    """«26 окт.» — короткая дата для строки риска и раскрытий."""
    if value is None:
        return ""
    local = to_local(value, tutor)
    return f"{local.day} {_MONTHS_SHORT[local.month - 1]}"


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        week_rate_label=week_rate_label,
        percent_label=percent_label,
        percent_or_dash=percent_or_dash,
        hours_label=hours_label,
        hours_phrase=hours_phrase,
        conversion_label=conversion_label,
        kept_reason_label=kept_reason_label,
        activity_label=activity_label,
        lesson_datetime_label=lesson_datetime_label,
        day_label=day_label,
    )
