"""Запись расхода: создание (спека tutor-finance, «Внесение расхода»).

Расход — строка `expenses`, к счёту ученика отношения не имеет: баланс
ученика не меняется, пересчётов нет. Проверки дублируют форму (как в
`payment_writer`): форма могла быть отправлена криво или устаревшими
данными, валидация только на клиенте — не валидация.

`spent_at` строится как `occurred_at` платежа (design D15): дата из формы
плюс текущее локальное время педагога, перевод в UTC общим `to_utc`.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.common.services.tutor_time import now_local, to_utc
from app.finance.models.expense import Expense
from app.finance.services.expense_form import validate_expense_data


def _spent_at(data: dict, tutor) -> datetime:
    """Момент расхода: дата из формы + время сохранения в зоне педагога."""
    local_now = now_local(tutor)
    local_value = datetime.combine(
        data["date"], local_now.time().replace(tzinfo=None)
    )
    # Секунды обнуляются: подпись показывает минуты, и две траты одного дня
    # должны сортироваться по времени ввода, а не по долям секунды.
    return to_utc(local_value.replace(second=0, microsecond=0), tutor)


def create_expense(
    db: Session, tutor_id: str, data: dict, tutor
) -> tuple[Expense | None, list[str]]:
    """Создаёт расход; при ошибке ничего не сохраняет."""
    errors = validate_expense_data(data)
    if errors:
        db.rollback()
        return None, errors

    expense = Expense(
        tutor_id=tutor_id,
        amount=data["amount"],
        category=data["category"],
        comment=data.get("comment") or None,
        spent_at=_spent_at(data, tutor),
    )
    db.add(expense)
    db.commit()
    return expense, []
