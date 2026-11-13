"""Напоминание «сегодня занятие, а на счёте не хватает денег».

Баннер отвечает на один вопрос: хватает ли денег на сегодняшние занятия.
Источники уже есть и дублировать их нельзя:

* уроки дня — `daily_digest.digest_lessons()`: только «Запланированные»,
  окно дня в зоне педагога, цены по единственному правилу модуля finance
  (`price_override ?? group.price_per_lesson`);
* деньги — `finance.services.balance`: `balance()` и `shortfall()`.

Направление импорта `lesson → finance` уже существует (`daily_digest` →
`charges`), обратного импорта сервис не создаёт.

Правила подсчёта:

* уроки берутся только «Запланированные» и только текущего дня педагога —
  в том числе уже прошедшие по времени, но не отмеченные: деньги за них
  всё ещё нужны. Отменённые, перенесённые и проведённые не участвуют;
* по каждому ученику складываются цены его целей за день, и нехватка
  считается от суммы (`shortfall(balance, сумма)`) — у ученика с двумя
  занятиями сравнивать баланс с одной ценой было бы неверно;
* цель без цены (`price is None`) в сумму не входит: сравнивать не с чем;
* в плашку попадают только ученики с нехваткой больше нуля.

Сервис не знает про FastAPI: на вход — сессия и карточка педагога, на
выход — словарь для шаблона или `None`, когда показывать нечего.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.finance.services.balance import balance, shortfall
from app.lesson.services.daily_digest import digest_lessons


def today_balance_notice(
    db: Session,
    tutor,
    *,
    day: date | None = None,
) -> dict | None:
    """Данные плашки о нехватке денег на уроки дня; нечего показать — `None`.

    `students` — число учеников (уникальных, а не число уроков), `missing` —
    сумма их нехваток, `student_ids` — состав для ключа клиентского
    закрытия. Уроков на день нет или денег хватает — `None`.

    Балансы считаются по одному вызову `balance()` на ученика: формула
    баланса живёт в одном месте, а число учеников дня ограничено
    расписанием. При росте нагрузки это станет N+1 — тогда нужен агрегат
    в модуле finance, но не вторая копия формулы здесь.
    """
    lessons = digest_lessons(db, tutor, day)

    # Цены целей складываются по ученику: у одного ученика за день может
    # быть несколько занятий, и нехватка считается от общей стоимости.
    prices_by_student: dict[str, int] = {}
    for lesson in lessons:
        for target in lesson.targets:
            if target.price is None:
                continue
            prices_by_student[target.student_id] = (
                prices_by_student.get(target.student_id, 0) + target.price
            )

    missing_by_student = {
        student_id: missing
        for student_id, price in prices_by_student.items()
        if (missing := shortfall(balance(db, student_id), price)) > 0
    }
    if not missing_by_student:
        return None

    student_ids = sorted(missing_by_student)
    return {
        "students": len(student_ids),
        "missing": sum(missing_by_student.values()),
        "student_ids": student_ids,
    }
