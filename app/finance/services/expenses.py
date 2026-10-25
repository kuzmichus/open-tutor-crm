"""Выборки расходов репетитора.

Сводка и список операций фильтруют траты тем же окном `[start, end)` по
`spent_at`, что и операции счёта по `occurred_at`: период один на всю
страницу, и «Расходы» в сводке обязаны совпасть с суммой строк вкладки
«Расходы».

Сервис не знает про FastAPI: на вход — сессия, репетитор и окно,
на выход — сумма или ORM-строки.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.finance.models.expense import Expense


def period_expenses(db: Session, tutor_id: str, *, start, end) -> int:
    """Сумма трат репетитора за окно `[start, end)`.

    `start is None` — окно не задано («Всё время»), фильтр по дате не нужен.
    """
    conditions = [Expense.tutor_id == tutor_id]
    if start is not None:
        conditions.append(Expense.spent_at >= start)
    if end is not None:
        conditions.append(Expense.spent_at < end)

    total = db.scalar(
        select(func.sum(Expense.amount)).where(*conditions)
    )
    return total or 0


def period_expense_rows(
    db: Session, tutor_id: str, *, start, end
) -> list[Expense]:
    """Траты репетитора за окно, от новых к старым (вторичный ключ —
    `created_at`: две траты одной даты не должны меняться местами)."""
    conditions = [Expense.tutor_id == tutor_id]
    if start is not None:
        conditions.append(Expense.spent_at >= start)
    if end is not None:
        conditions.append(Expense.spent_at < end)

    return list(
        db.scalars(
            select(Expense)
            .where(*conditions)
            .order_by(Expense.spent_at.desc(), Expense.created_at.desc())
        ).all()
    )
