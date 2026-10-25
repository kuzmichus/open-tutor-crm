"""Сводка страницы финансов: поток за период и балансы на сейчас (design D3).

Два рода чисел, и подписи карточек это подчёркивают:

- **Поток за период** — операции в окне `[start, end)` по `occurred_at`
  («Расходы» — по `spent_at` той же таблицы трат): «Доход» (оплаченные
  платежи), «Возвраты», «Чистый доход», «Расходы», «Заработано (уроки)».
  Считаются запросами `GROUP BY kind` c JOIN по владельцу ученика — N+1
  на карточку здесь недопустим.
- **Состояние на сейчас** — «Долги учеников» и «Переплата»: суммы
  отрицательных и положительных балансов всех учеников. Баланс —
  производная (design D3 student-finance), поэтому считается той же
  формулой `signed_amount` в Python по операциям, сгруппированным по
  ученику: второй копии правила денег не появляется.

Блок «Заработано и получено» — арифметика по референсу: заработано
уроками, получено от учеников, минус расходы — и итог «Осталось
репетитору» (получено минус расходы, то же число, что «Чистая прибыль»).

Сервис не знает про FastAPI: на вход — сессия, репетитор и период,
на выход — словарь для `finance/_summary.html`.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import signed_amount
from app.finance.services.expenses import period_expenses
from app.student.models.student import Student


def period_flow(db: Session, tutor_id: str, *, start, end) -> dict[str, int]:
    """Суммы операций за окно по видам: `income`, `refunds`, `earned`.

    В доход входят только оплаченные платежи (`status='paid'`): ожидающие
    и отменённые — это обещания, а не деньги (design D4 student-finance).
    Возвраты и списания входят всегда: статуса у них нет.
    """
    conditions = [Student.tutor_id == tutor_id]
    if start is not None:
        conditions.append(AccountOperation.occurred_at >= start)
    if end is not None:
        conditions.append(AccountOperation.occurred_at < end)

    rows = db.execute(
        select(AccountOperation.kind, AccountOperation.status, func.sum(AccountOperation.amount))
        .join(Student, Student.id == AccountOperation.student_id)
        .where(*conditions)
        .group_by(AccountOperation.kind, AccountOperation.status)
    ).all()

    income = refunds = earned = 0
    for kind, status_value, total in rows:
        if kind == "payment" and status_value == "paid":
            income += total
        elif kind == "refund":
            refunds += total
        elif kind == "lesson":
            earned += total
    return {"income": income, "refunds": refunds, "earned": earned}


def balance_sides(db: Session, tutor_id: str) -> dict[str, int]:
    """Долги и переплаты учеников на текущий момент.

    Один запрос операций с JOIN по владельцу, суммы — в Python той же
    формулой, что показывает баланс карточки: числа здесь и в карточке
    ученика не могут разойтись.
    """
    rows = db.execute(
        select(
            AccountOperation.student_id,
            AccountOperation.kind,
            AccountOperation.status,
            AccountOperation.amount,
        )
        .join(Student, Student.id == AccountOperation.student_id)
        .where(Student.tutor_id == tutor_id)
    ).all()

    per_student: dict[str, int] = {}
    for student_id, kind, status_value, amount in rows:
        per_student[student_id] = (
            per_student.get(student_id, 0) + signed_amount(kind, status_value, amount)
        )

    return {
        "debts": sum(value for value in per_student.values() if value < 0),
        "overpayments": sum(value for value in per_student.values() if value > 0),
    }


def compare_note(received: int, earned: int) -> str:
    """Подсказка блока «Заработано и получено» о разнице сумм (design D4)."""
    if received > earned:
        return (
            "Получено больше заработанного: ученики платят вперёд, "
            "за будущие занятия."
        )
    if received < earned:
        return (
            "Получено меньше заработанного: ученики должны "
            "за прошедшие занятия."
        )
    return "Полученное совпадает с заработанным."


def summary_context(db: Session, tutor_id: str, *, start, end) -> dict:
    """Контекст `finance/_summary.html`: суммы, прибыль и сравнение."""
    flow = period_flow(db, tutor_id, start=start, end=end)
    sides = balance_sides(db, tutor_id)
    expenses = period_expenses(db, tutor_id, start=start, end=end)

    net_income = flow["income"] - flow["refunds"]
    received = net_income
    profit = net_income - expenses
    return {
        "income": flow["income"],
        "refunds": flow["refunds"],
        "net_income": net_income,
        "expenses": expenses,
        "profit": profit,
        # «= Осталось репетитору» блока сравнения: получено минус расходы.
        # Число совпадает с «Чистой прибылью» — это одно и то же правило
        # денег под двумя подписями (сводка и арифметика блока).
        "left_for_tutor": profit,
        # Отрицательный итог (расходы превысили полученное) красится красным:
        # класс решает сервер, шаблон знак не разбирает.
        "left_is_negative": profit < 0,
        "earned": flow["earned"],
        "debts": sides["debts"],
        "overpayments": sides["overpayments"],
        "compare_note": compare_note(received, flow["earned"]),
    }
