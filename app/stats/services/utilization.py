"""Блок «Загрузка (Utilization)»: факт к цели и факт к максимуму.

Два процента отвечают на два разных вопроса репетитора:

- **факт к цели** — сколько отработано от комфортной нагрузки
  (`tutor_settings.weekly_load_hours`, задаётся в профиле вручную);
- **факт к максимуму** — сколько отработано от времени, которое физически
  доступно по рабочему шаблону (см. `availability`).

Цель задана в часах **в неделю**, а период «Обзора» может быть любым,
поэтому она масштабируется на длину периода: `weekly_load_hours × дни / 7`.
Иначе «Всё время» сравнивало бы месяцы работы с недельной нормой.

Цветовая индикация — из ТЗ: меньше 70% — недогруз (жёлтый), 70–90% —
норма (зелёный), больше 90% — риск выгорания (красный). Значения 85–90%
ТЗ не описывает; они попадают в «норму», чтобы не красить красным
безобидные 88%.

Ширина полосы (`target_bar`/`max_bar`) зажата в 0..100: переработка
показывается полностью заполненной полосой, а не вылезает за карточку.
"""

from sqlalchemy.orm import Session

from app.stats.services.availability import period_days
from app.stats.services.hours import MINUTES_PER_HOUR, minutes_to_hours
from app.tutor.services.settings import get_settings

# Тона полос: классы `stats-util__bar--<tone>` в styles.css.
TONE_OK = "ok"
TONE_LOW = "low"
TONE_HIGH = "high"
TONE_NONE = "none"

# Пороги из ТЗ, проценты.
LOW_PERCENT = 70
HIGH_PERCENT = 90

# Дней в неделе: база для масштабирования недельной цели на период.
WEEK_DAYS = 7

# Подсказка под блоком. Первое предложение — формулировка ТЗ; второе честно
# говорит, что перерывы внутри дня пока не вычитаются: почасового шаблона
# недели и обедов в настройках проекта нет.
AVAILABILITY_HINT = (
    "Доступные часы рассчитаны по вашему рабочему шаблону за вычетом "
    "отпусков и перерывов. Перерывы внутри рабочего дня пока не учитываются."
)


def percent_of(part: int, total: int) -> int | None:
    """Доля в процентах; нулевой знаменатель — `None` («—», а не «0%»)."""
    if not total or total <= 0:
        return None
    return round(part / total * 100)


def tone(percent: int | None) -> str:
    """Тон полосы по проценту: недогруз / норма / риск выгорания."""
    if percent is None:
        return TONE_NONE
    if percent < LOW_PERCENT:
        return TONE_LOW
    if percent > HIGH_PERCENT:
        return TONE_HIGH
    return TONE_OK


def _bar(percent: int | None) -> int:
    """Ширина полосы в процентах с зажимом в 0..100."""
    if percent is None:
        return 0
    return min(100, max(0, percent))


def utilization_context(
    db: Session,
    tutor,
    *,
    start,
    end,
    actual_minutes: int,
    available_minutes: int,
    days: int | None = None,
) -> dict:
    """Контекст блока «Загрузка»: часы, проценты, тона и подсказка.

    `actual_minutes`/`available_minutes` приходят готовыми: их считают
    `hours.completed_minutes` и `availability.available_minutes`, чтобы блок
    не делал собственных запросов и не расходился с остальными карточками.

    `days` — длина периода в локальных сутках. «Обзор» передаёт её готовой:
    то же число нужно блоку внеурочной занятости, и второй перебор дат на
    страницу был бы лишней работой. Без аргумента считается здесь — так
    функцию можно звать изолированно.
    """
    if days is None:
        days = len(period_days(tutor, start=start, end=end))
    weekly_hours = get_settings(db, tutor.id).weekly_load_hours
    target_minutes = (
        weekly_hours * MINUTES_PER_HOUR * days / WEEK_DAYS
        if weekly_hours
        else None
    )
    fact_to_target = (
        percent_of(actual_minutes, round(target_minutes))
        if target_minutes
        else None
    )
    fact_to_max = percent_of(actual_minutes, available_minutes)
    return {
        "days": days,
        "actual_hours": minutes_to_hours(actual_minutes),
        "available_hours": minutes_to_hours(available_minutes),
        "target_hours": (
            minutes_to_hours(round(target_minutes)) if target_minutes else None
        ),
        "fact_to_target": fact_to_target,
        "fact_to_max": fact_to_max,
        "target_bar": _bar(fact_to_target),
        "max_bar": _bar(fact_to_max),
        "target_tone": tone(fact_to_target),
        "max_tone": tone(fact_to_max),
        # Цель не задана в профиле — вместо процента шаблон покажет подсказку
        # со ссылкой на настройки, а не «0%».
        "target_missing": not weekly_hours,
        "hint": AVAILABILITY_HINT,
    }
