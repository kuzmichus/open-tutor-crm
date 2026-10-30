"""Финансы по детям для вкладки «Финансы» кабинета родителя (design D8).

Для каждого привязанного ребёнка: баланс (`finance/services/balance.py` —
та же формула, что в CRM), сумма пополнений и история операций
(`finance/services/operations.py` — тот же список, что видит репетитор).
Общий итог — сумма балансов детей; без плательщика в формуле: плательщик —
роль для расчётов, а не разграничение видимости (решение владельца).

История показывается по-ребёночи, а не общим потоком: родителю важно
видеть, за кого пришли или ушли деньги.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.services.children import children
from app.finance.models.account_operation import BALANCE_PAYMENT_STATUS, AccountOperation
from app.finance.services.balance import balance
from app.finance.services.operations import student_history
from app.student.models.student import Student


def payments_total(db: Session, student_id: str) -> int:
    """Сумма пополнений ребёнка: оплаченные платежи, без возвратов.

    В сумму входят только платежи, влияющие на баланс (`BALANCE_PAYMENT_STATUS`)
    — иначе карточка «пополнений» разошлась бы с балансом, где «Ожидает»
    и «Отменено» не участвуют.
    """
    rows = db.scalars(
        select(AccountOperation.amount).where(
            AccountOperation.student_id == student_id,
            AccountOperation.kind == "payment",
            AccountOperation.status == BALANCE_PAYMENT_STATUS,
        )
    ).all()
    return sum(rows)


@dataclass(frozen=True)
class ChildFinance:
    """Финансовый блок одного ребёнка на вкладке «Финансы»."""

    student: Student
    balance: int
    payments_total: int
    history: list[AccountOperation]


def finance_overview(db: Session, contact_id: str) -> tuple[list[ChildFinance], int]:
    """Блоки по детям и общий итог (сумма балансов), в порядке навигации."""
    blocks: list[ChildFinance] = []
    for student in children(db, contact_id):
        blocks.append(
            ChildFinance(
                student=student,
                balance=balance(db, student.id),
                payments_total=payments_total(db, student.id),
                history=student_history(db, student.id),
            )
        )
    return blocks, sum(block.balance for block in blocks)
