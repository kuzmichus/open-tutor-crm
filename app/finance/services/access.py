"""Доступ к операциям счёта: `get_owned_operation` через ученика.

У операции нет своего `tutor_id` (design D2): владелец выводится из
ученика, как владелец урока выводится из цели, а у брони — из окна.
Поэтому доступ проверяется одним `SELECT` с `JOIN students` по `id`
операции и `tutor_id` ученика — без второго запроса на проверку владельца.

Чужая и несуществующая операция неразличимы: 404, а не 403 — существование
чужой записи не раскрывается (спека student-finance, «Изоляция счёта по
репетитору»).

Ри-экспорт `require_tutor_id`/`LoginRequired`, а также `get_owned_student`
и `get_owned_group` — по правилу AGENTS.md: вьюхи модуля не зависят от
чужих модулей и `common` напрямую.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.access import LOGIN_URL, LoginRequired, require_tutor_id
from app.finance.models.account_operation import AccountOperation
from app.finance.models.expense import Expense
from app.group.services.access import get_owned_group
from app.student.models.student import Student
from app.student.services.access import get_owned_student

__all__ = [
    "LOGIN_URL",
    "LoginRequired",
    "get_owned_expense",
    "get_owned_group",
    "get_owned_operation",
    "get_owned_student",
    "require_tutor_id",
]


def get_owned_operation(
    db: Session, operation_id: str, tutor_id: str
) -> AccountOperation:
    """Операция счёта ученика этого репетитора либо 404.

    Единое правило выборки одной операции: `id` операции и `tutor_id`
    ученика проверяются одним запросом.
    """
    operation = db.scalars(
        select(AccountOperation)
        .join(Student, Student.id == AccountOperation.student_id)
        .where(
            AccountOperation.id == operation_id,
            Student.tutor_id == tutor_id,
        )
    ).one_or_none()
    if operation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return operation


def get_owned_expense(db: Session, expense_id: str, tutor_id: str) -> Expense:
    """Расход этого репетитора либо 404.

    У расхода есть своя колонка `tutor_id` (владельца выводить не из кого),
    поэтому проверка — один `SELECT` без JOIN. Чужая и несуществующая
    запись неразличимы: 404, а не 403.
    """
    expense = db.scalars(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.tutor_id == tutor_id,
        )
    ).one_or_none()
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return expense
