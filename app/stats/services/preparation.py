"""Внеурочная занятость: подготовка к урокам и проверка домашних заданий.

Учебные часы — только видимая часть работы: за каждым проведённым уроком
стоит подготовка к нему и проверка домашнего задания. Их объём задаёт
«Коэффициент подготовки» профиля (`tutor_settings.preparation_coefficient`,
доля длительности урока). Блок отвечает на вопрос «сколько я на самом деле
работаю», а не «сколько я провёл у доски».

Расчёт:

- база — фактические минуты периода (`hours.completed_minutes`): групповой
  урок считается один раз, пробные входят как реально потраченное время;
- подготовка = `фактические минуты × коэффициент`;
- общая занятость = фактические минуты + подготовка;
- недельные значения — минуты периода × 7 / число дней периода: порог
  выгорания задан в часах **в неделю**, а период «Обзора» может быть любым.

Уровни недельной нагрузки (комфорт / высокая / риск выгорания) и пороги
живут в `workload`: по ним же красится шкала «Загрузка ресурса» и
показывается алерт. Один источник правды не даёт инсайту, шкале и алерту
разойтись в трактовке «много это сколько».

Шаблон не считает бизнес-данные: он получает готовые подписи и геометрию
пончика (правило модуля stats).
"""

import math
from decimal import Decimal

from sqlalchemy.orm import Session

from app.stats.services import workload
from app.stats.services.hours import minutes_to_hours
from app.stats.services.presentation import hours_label, hours_phrase
from app.tutor.services.settings import get_settings

# Геометрия пончика «Уроки vs Подготовка» (SVG, пиксели).
DONUT_SIZE = 140
DONUT_RADIUS = 54
DONUT_WIDTH = 16

# Тексты блока. Собираются здесь, а не в шаблоне: числа и склонения —
# бизнес-данные, шаблон только печатает готовые строки.
NO_LESSONS_TEXT = (
    "За период нет проведённых уроков — подготовки к ним тоже нет."
)
NO_PREPARATION_TEXT = (
    "Коэффициент подготовки равен 0, поэтому внеурочное время не "
    "учитывается. Поставьте коэффициент в профиле, если готовитесь к урокам."
)


def coefficient_label(value: Decimal | float) -> str:
    """Коэффициент для подписи: «0,7», «1,2», «2» — без хвостовых нулей.

    Публичная: ту же подпись печатает страница финансов («подготовка по
    коэффициенту 0,7»), и второй форматтер разошёлся бы со «Статистикой».
    """
    number = float(value)
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if text else "0"


def preparation_minutes(actual_minutes: int, coefficient: float) -> int:
    """Сколько минут подготовки приходится на `actual_minutes` уроков.

    Публичная и единственная формула внеурочной занятости: «Статистика»
    показывает по ней часы подготовки, «Финансы» — реальную стоимость
    часа. Своя копия в финансах дала бы другое число минут на тех же
    данных. Отрицательный коэффициент (теоретически возможный при кривых
    данных) не вычитает время: подготовки не меньше нуля.
    """
    return max(0, round(actual_minutes * coefficient))


def minutes_per_hour(coefficient: float) -> int:
    """Сколько минут подготовки приходится на час урока."""
    return round(coefficient * 60)


def _chart(lesson_minutes: int, preparation_minutes: int) -> dict | None:
    """Геометрия SVG-пончика: дуга уроков и дуга подготовки.

    Доли считаются от общей занятости, поэтому кольцо всегда замкнуто.
    Дуги начинаются сверху (поворот `-90°` в шаблоне) и идут по часовой
    стрелке: сначала уроки, затем подготовка — так же, как в легенде.
    Нулевая подготовка даёт кольцо, целиком занятое уроками.
    """
    total = lesson_minutes + preparation_minutes
    if total <= 0:
        return None
    circumference = 2 * math.pi * DONUT_RADIUS
    lesson_dash = round(circumference * lesson_minutes / total, 1)
    return {
        "size": DONUT_SIZE,
        "ring_radius": DONUT_RADIUS,
        "width": DONUT_WIDTH,
        "center": DONUT_SIZE / 2,
        "circumference": round(circumference, 1),
        "lesson_dash": lesson_dash,
        "prep_dash": round(circumference - lesson_dash, 1),
        # Подготовка начинается там, где закончились уроки: отрицательное
        # смещение сдвигает её дугу вперёд по кольцу.
        "prep_offset": -lesson_dash,
    }


def _legend(lesson_minutes: int, preparation_minutes: int) -> list[dict]:
    """Строки легенды: «Уроки: 20 ч», «Подготовка: 10 ч», «Всего: 30 ч»."""
    total = lesson_minutes + preparation_minutes
    rows = (
        ("lesson", "Уроки", lesson_minutes),
        ("preparation", "Подготовка", preparation_minutes),
        ("total", "Всего", total),
    )
    legend = []
    for key, label, minutes in rows:
        percent = round(minutes / total * 100) if total > 0 else 0
        legend.append(
            {
                "key": key,
                "label": label,
                "value": hours_label(minutes_to_hours(minutes)),
                "percent": percent,
            }
        )
    return legend


def _weekly_phrase(total_minutes: int, days: int) -> str:
    """Общая занятость, пересчитанная на неделю: «35 часов»."""
    if days <= 0:
        return hours_phrase(minutes_to_hours(total_minutes))
    weekly = minutes_to_hours(workload.weekly_minutes(total_minutes, days))
    return hours_phrase(weekly)


def _insight(
    *,
    coefficient: float,
    has_lessons: bool,
    weekly_total_minutes: int,
    days: int,
) -> str:
    """Подпись-инсайт под блоком «Загрузка» (формулировка задачи).

    Последнее предложение — вердикт по абсолютной недельной занятости:
    «Это комфортный уровень нагрузки», «Это высокий уровень нагрузки» или
    «Высокий риск выгорания!». Без него подпись сообщала бы число, но не
    отвечала на вопрос «и что мне с этим делать».
    """
    if not has_lessons:
        return NO_LESSONS_TEXT
    if coefficient <= 0:
        return NO_PREPARATION_TEXT
    per_hour = minutes_per_hour(coefficient)
    phrase = _weekly_phrase(weekly_total_minutes, days)
    weekly_hours = minutes_to_hours(
        workload.weekly_minutes(weekly_total_minutes, days)
    )
    verdict = workload.verdict(weekly_hours)
    return (
        f"С учётом подготовки (около {per_hour} мин на час урока) ваша "
        f"общая занятость составляет {phrase} в неделю. {verdict}"
    )


def _alert(
    *,
    has_lessons: bool,
    weekly_lesson_minutes: int,
    weekly_preparation_minutes: int,
    days: int,
) -> dict | None:
    """Алерт выгорания, если недельная общая занятость выше порога.

    Порог тот же, что у красной «Загрузки ресурса» (`workload`): больше
    45 часов в неделю. Ровно 45 — ещё высокая, но допустимая нагрузка,
    предупреждение начинается со следующей минуты.
    """
    if not has_lessons or days <= 0:
        return None
    weekly_total_minutes = weekly_lesson_minutes + weekly_preparation_minutes
    weekly_hours = minutes_to_hours(
        workload.weekly_minutes(weekly_total_minutes, days)
    )
    if workload.level(weekly_hours) != workload.LEVEL_BURNOUT:
        return None
    lesson_phrase = _weekly_phrase(weekly_lesson_minutes, days)
    preparation_phrase = _weekly_phrase(weekly_preparation_minutes, days)
    total_phrase = _weekly_phrase(weekly_total_minutes, days)
    return {
        "text": (
            f"Учебная нагрузка {lesson_phrase} + подготовка "
            f"{preparation_phrase} = {total_phrase} работы в неделю. "
            "Высокий риск выгорания. Рассмотрите повышение цен или "
            "сокращение учеников."
        ),
        "weekly_total_hours": weekly_hours,
        "threshold": workload.HIGH_WEEKLY_HOURS,
        "level": workload.LEVEL_BURNOUT,
    }


def preparation_context(
    db: Session,
    tutor,
    *,
    actual_minutes: int,
    days: int,
) -> dict:
    """Контекст внеурочной занятости: часы, инсайт, алерт и геометрия.

    `actual_minutes` приходит готовым из `hours.completed_minutes` (та же
    база, что у блока «Загрузка»), `days` — длина периода в локальных
    сутках из `availability.period_days`: оба значения уже посчитаны на
    странице, повторных запросов здесь нет.
    """
    coefficient = float(get_settings(db, tutor.id).preparation_coefficient or 0)
    prep_minutes = preparation_minutes(actual_minutes, coefficient)
    total_minutes = actual_minutes + prep_minutes
    has_lessons = actual_minutes > 0
    weekly_total_hours = minutes_to_hours(
        workload.weekly_minutes(total_minutes, days)
    )

    return {
        "coefficient": coefficient,
        "coefficient_label": coefficient_label(coefficient),
        "minutes_per_hour": minutes_per_hour(coefficient),
        "has_lessons": has_lessons,
        "has_preparation": prep_minutes > 0,
        "lesson_hours": minutes_to_hours(actual_minutes),
        "preparation_hours": minutes_to_hours(prep_minutes),
        "preparation_minutes": prep_minutes,
        "total_hours": minutes_to_hours(total_minutes),
        "weekly_lesson_hours": minutes_to_hours(
            workload.weekly_minutes(actual_minutes, days)
        ),
        "weekly_preparation_hours": minutes_to_hours(
            workload.weekly_minutes(prep_minutes, days)
        ),
        "weekly_total_hours": weekly_total_hours,
        # Уровень недельной нагрузки: по нему красятся шкала и инсайт.
        "level": workload.level(weekly_total_hours) if has_lessons else None,
        "insight": _insight(
            coefficient=coefficient,
            has_lessons=has_lessons,
            weekly_total_minutes=total_minutes,
            days=days,
        ),
        "alert": _alert(
            has_lessons=has_lessons,
            weekly_lesson_minutes=actual_minutes,
            weekly_preparation_minutes=prep_minutes,
            days=days,
        ),
        "legend": _legend(actual_minutes, prep_minutes),
        "chart": _chart(actual_minutes, prep_minutes),
    }
