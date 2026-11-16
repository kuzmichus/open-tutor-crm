"""Плашки-предупреждения кабинета родителя (design D6).

Зеркало репетиторского каркаса: «на сегодня занятие, а денег не хватает»
и «задолженность за прошедшие уроки», но по детям контакта. Формулы не
дублируются:

* нехватка — переиспользует `digest_lessons(db, tutor, day)` (цены по
  единственному правилу модуля finance, «уже прошедшие по времени, но не
  отмеченные» остаются в одном месте) и фильтрует цели по id детей
  контакта; `shortfall` — та же функция `finance.services.balance`;
* задолженность — отрицательный `balance()` каждого ребёнка: баланс
  не ограничен снизу нулём, отрицательное значение и есть долг.

Импорт `cabinet → lesson/finance` согласуется с существующим
направлением (`cabinet/services/calendar.py` уже тянет `calendar`,
`child_finance.py` — `finance`). Сервис не знает про FastAPI: на вход —
сессия, дети контакта и карточка репетитора, на выход — словарь для
шаблона или `None`.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.common.services.tutor_time import today_local
from app.finance.services.balance import balance, shortfall
from app.lesson.services.daily_digest import digest_lessons
from app.student.models.student import Student


def today_shortfall_notice(
    db: Session,
    tutor,
    children: list[Student],
    *,
    day: date | None = None,
) -> dict | None:
    """Нехватка денег на сегодняшние занятия детей; показывать нечего — `None`.

    Уроки дня репетитора берутся целиком (`digest_lessons`), из целей
    остаются только дети контакта: уроки других учеников педагога на
    баланс детей не влияют. По каждому ребёнку цены его целей за день
    складываются, и нехватка считается от суммы — `shortfall(balance,
    сумма)`, как у репетиторской плашки.

    Возвращается `{students, missing, student_ids, day}` — состав для
    подписи и для ключа клиентского закрытия. День обязателен в ключе:
    закрытое сегодня напоминание с тем же составом и суммой молча скрыло
    бы завтрашний долг.
    """
    child_ids = {child.id for child in children}
    if not child_ids:
        return None

    day = day or today_local(tutor)
    lessons = digest_lessons(db, tutor, day)

    # Цены целей складываются по ребёнку: у одного ребёнка за день может
    # быть несколько занятий, и нехватка считается от общей стоимости.
    prices_by_child: dict[str, int] = {}
    for lesson in lessons:
        for target in lesson.targets:
            if target.student_id not in child_ids or target.price is None:
                continue
            prices_by_child[target.student_id] = (
                prices_by_child.get(target.student_id, 0) + target.price
            )

    missing_by_child = {
        student_id: missing
        for student_id, price in prices_by_child.items()
        if (missing := shortfall(balance(db, student_id), price)) > 0
    }
    if not missing_by_child:
        return None

    student_ids = sorted(missing_by_child)
    return {
        "students": len(student_ids),
        "missing": sum(missing_by_child.values()),
        "student_ids": student_ids,
        "day": day,
    }


def debt_notice(db: Session, children: list[Student]) -> dict | None:
    """Долг за прошедшие уроки: дети с отрицательным балансом; нет — `None`.

    Задолженность = отрицательный баланс (решение владельца): возвраты и
    списания могут увести баланс ниже нуля, и это долг, который надо
    покрыть. Возвращается `{names, total, student_ids}`: имена — в
    порядке навигации (алфавит), сумма — общий долг по детям для
    подписи и ключа закрытия.
    """
    debtors: list[dict] = []
    for child in children:
        child_balance = balance(db, child.id)
        if child_balance < 0:
            debtors.append(
                {
                    "id": child.id,
                    "name": child.first_name or child.last_name or "",
                    "amount": -child_balance,
                }
            )
    if not debtors:
        return None

    return {
        "names": [debtor["name"] for debtor in debtors],
        "total": sum(debtor["amount"] for debtor in debtors),
        # Состав для ключа клиентского закрытия: дети с долгом и суммы.
        "student_ids": sorted(debtor["id"] for debtor in debtors),
    }
