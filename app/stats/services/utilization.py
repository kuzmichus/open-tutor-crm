"""Блок «Загрузка (Utilization)»: факт к цели и загрузка ресурса.

Две шкалы отвечают на два разных вопроса репетитора и поэтому красятся
по-разному:

- **факт к цели** — сколько отработано от комфортной нагрузки
  (`tutor_settings.weekly_load_hours`, задаётся в профиле вручную).
  Цель задана в часах **в неделю**, а период «Обзора» может быть любым,
  поэтому она масштабируется на длину периода: `weekly_load_hours × дни / 7`.
  Тон — по проценту: меньше 70% — недогруз (жёлтый), 70–100% — норма
  (зелёный), больше 100% — взял больше, чем планировал (красный).
- **загрузка ресурса** — сколько занимает **общая** работа (уроки плюс
  подготовка) от времени, которое физически доступно по рабочему шаблону
  (см. `availability`). Тон — по абсолютным часам **в неделю**, а не по
  проценту: 90% от 90 доступных часов — это 81 час работы, физически
  невозможная нагрузка, а 36% тех же часов (32,7 часа) — отличная норма.
  Процент на полосе остаётся справочной цифрой, цвет говорит о нагрузке.

Уровни недельной нагрузки и их границы (35 и 45 часов) живут в `workload`:
там же их читают инсайт-вердикт и алерт выгорания.

Ширина полосы (`target_bar`/`resource_bar`) зажата в 0..100: переработка
показывается полностью заполненной полосой, а не вылезает за карточку.
"""

from sqlalchemy.orm import Session

from app.stats.services import workload
from app.stats.services.availability import period_days
from app.stats.services.hours import MINUTES_PER_HOUR, minutes_to_hours
from app.tutor.services.settings import get_settings

# Тона полос: классы `stats-util__bar--<tone>` в styles.css.
TONE_OK = "ok"
TONE_WARN = "warn"
TONE_DANGER = "danger"
TONE_NONE = "none"

# Пороги «факта к цели», проценты: < 70 — недогруз, 70–100 — норма,
# > 100 — больше запланированного.
LOW_PERCENT = 70
OVER_PERCENT = 100

# Дней в неделе: база для масштабирования недельной цели на период.
WEEK_DAYS = 7

# Подсказка под блоком. Первое предложение — формулировка ТЗ; второе честно
# говорит, что перерывы внутри дня пока не вычитаются: почасового шаблона
# недели и обедов в настройках проекта нет.
AVAILABILITY_HINT = (
    "Доступные часы рассчитаны по вашему рабочему шаблону за вычетом "
    "отпусков и перерывов. Перерывы внутри рабочего дня пока не учитываются."
)

# Уровень недельной нагрузки → тон полосы «Загрузка ресурса».
_LEVEL_TONES = {
    workload.LEVEL_COMFORT: TONE_OK,
    workload.LEVEL_HIGH: TONE_WARN,
    workload.LEVEL_BURNOUT: TONE_DANGER,
}


def percent_of(part: int, total: int) -> int | None:
    """Доля в процентах; нулевой знаменатель — `None` («—», а не «0%»)."""
    if not total or total <= 0:
        return None
    return round(part / total * 100)


def tone(percent: int | None) -> str:
    """Тон «факта к цели» по проценту: недогруз / норма / перегруз."""
    if percent is None:
        return TONE_NONE
    if percent < LOW_PERCENT:
        return TONE_WARN
    if percent > OVER_PERCENT:
        return TONE_DANGER
    return TONE_OK


def resource_tone(weekly_hours: float) -> str:
    """Тон «Загрузки ресурса» по абсолютной недельной занятости.

    Процент от доступных часов здесь сознательно не участвует: 50% от
    большого календаря — это всё равно 45 часов работы в неделю.
    """
    return _LEVEL_TONES[workload.level(weekly_hours)]


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
    preparation_minutes: int = 0,
    days: int | None = None,
) -> dict:
    """Контекст блока «Загрузка»: часы, проценты, тона и подсказка.

    `actual_minutes`/`available_minutes` приходят готовыми: их считают
    `hours.completed_minutes` и `availability.available_minutes`, чтобы блок
    не делал собственных запросов и не расходился с остальными карточками.
    `preparation_minutes` — подготовка к урокам и проверка ДЗ: вторая шкала
    сравнивает с календарём именно общую занятость, а не только уроки.

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
    # Общая занятость — то, из чего складывается реальная рабочая неделя.
    resource_minutes = actual_minutes + preparation_minutes
    resource_percent = percent_of(resource_minutes, available_minutes)
    weekly_resource_hours = minutes_to_hours(
        workload.weekly_minutes(resource_minutes, days)
    )
    return {
        "days": days,
        "actual_hours": minutes_to_hours(actual_minutes),
        "preparation_hours": minutes_to_hours(preparation_minutes),
        "resource_hours": minutes_to_hours(resource_minutes),
        "available_hours": minutes_to_hours(available_minutes),
        "target_hours": (
            minutes_to_hours(round(target_minutes)) if target_minutes else None
        ),
        "fact_to_target": fact_to_target,
        "resource_percent": resource_percent,
        "weekly_resource_hours": weekly_resource_hours,
        "target_bar": _bar(fact_to_target),
        "resource_bar": _bar(resource_percent),
        "target_tone": tone(fact_to_target),
        "resource_tone": resource_tone(weekly_resource_hours),
        # Цель не задана в профиле — вместо процента шаблон покажет подсказку
        # со ссылкой на настройки, а не «0%».
        "target_missing": not weekly_hours,
        "hint": AVAILABILITY_HINT,
    }
