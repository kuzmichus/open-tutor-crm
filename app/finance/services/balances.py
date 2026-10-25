"""Балансы всех учеников репетитора для карточки «Балансы учеников».

Один запрос операций с JOIN по ученикам, суммы — в Python той же формулой
`signed_amount`, что считает баланс карточки ученика: числа здесь, в
карточке и в сводке не могут разойтись (второй копии правила денег нет).

Сервис не знает про FastAPI: на вход — сессия и репетитор, на выход —
строки для шаблона: имя, инициалы аватара и баланс.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import signed_amount
from app.student.models.student import Student


@dataclass(frozen=True)
class StudentBalance:
    """Ученик с ненулевым балансом: строка карточки «Балансы учеников»."""

    student_id: str
    name: str
    initials: str
    balance: int


def student_balances(db: Session, tutor_id: str) -> list[StudentBalance]:
    """Ненулевые балансы учеников репетитора, от большего долга к меньшему.

    Сортировка по модулю: и должники, и переплатчики идут от «самых
    заметных» сумм — карточку открывают, чтобы понять, с кого спрашивать.
    """
    rows = db.execute(
        select(
            AccountOperation.student_id,
            AccountOperation.kind,
            AccountOperation.status,
            AccountOperation.amount,
            Student.first_name,
            Student.last_name,
        )
        .join(Student, Student.id == AccountOperation.student_id)
        .where(Student.tutor_id == tutor_id)
    ).all()

    sums: dict[str, int] = {}
    names: dict[str, tuple[str, str]] = {}
    for student_id, kind, status_value, amount, first, last in rows:
        sums[student_id] = (
            sums.get(student_id, 0) + signed_amount(kind, status_value, amount)
        )
        names[student_id] = (first or "", last or "")

    def _initials(first: str, last: str) -> str:
        parts = [first[:1], last[:1]]
        return "".join(p for p in parts if p).upper() or "?"

    balances = [
        StudentBalance(
            student_id=student_id,
            name=f"{first} {last}".strip() or "Без имени",
            initials=_initials(first, last),
            balance=balance,
        )
        for student_id, balance in sums.items()
        if balance != 0
        for first, last in (names[student_id],)
    ]
    balances.sort(key=lambda row: abs(row.balance), reverse=True)
    return balances
