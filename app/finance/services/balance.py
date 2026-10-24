"""Баланс ученика: единственная формула модуля (design D3).

```
баланс = SUM(+amount  WHERE kind='payment' AND status='paid')
       − SUM( amount  WHERE kind='refund')
       − SUM( amount  WHERE kind='lesson')
```

Знак выводится из вида операции, а `amount` всегда положителен
(`ck_account_operations_amount`): хранить знак в сумме значило бы допустить
положительный «возврат», противоречащий виду.

Баланс не ограничивается снизу нулём: возврат 2 400 при балансе 300 даёт
−2 100, потому что репетитор возвращает деньги, уже потраченные на уроки
(спека student-finance, «Баланс ученика»).

Шаблон не суммирует ничего сам — он получает готовое число и вызывает
`money()` из `presentation.py`.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import (
    BALANCE_PAYMENT_STATUS,
    AccountOperation,
)
from app.tutor.services.clock import as_utc

# Виды операций, которые уменьшают баланс: сумма вычитается целиком.
DEBIT_KINDS = ("refund", "lesson")


def affects_balance(kind: str, status: str | None) -> bool:
    """Входит ли операция в баланс.

    Платёж — только в статусе «Оплачено»; «Ожидает» и «Отменено» видны в
    списке платежей, но баланс не меняют (design D4). Возвраты и списания
    входят всегда: у них статуса нет.
    """
    if kind == "payment":
        return status == BALANCE_PAYMENT_STATUS
    return kind in DEBIT_KINDS


def signed_amount(kind: str, status: str | None, amount: int) -> int:
    """Вклад операции в баланс: `+amount` для платежа, `−amount` для остальных.

    Единственная реализация формулы D3: её используют и `balance()`, и
    строка истории (`presentation.signed_money`). Дублировать правило
    в шаблоне нельзя — иначе число в карточке и сумма строк разойдутся.
    """
    if not affects_balance(kind, status):
        return 0
    return amount if kind == "payment" else -amount


def balance(db: Session, student_id: str) -> int:
    """Текущий баланс ученика в рублях (может быть отрицательным).

    Сумма считается в Python по трём колонкам одного `SELECT`: операций у
    одного ученика десятки, а одна формула в одном месте важнее экономии
    на агрегате — SQL-версия той же формулы стала бы второй её копией.
    """
    rows = db.execute(
        select(
            AccountOperation.kind,
            AccountOperation.status,
            AccountOperation.amount,
        ).where(AccountOperation.student_id == student_id)
    ).all()
    return sum(signed_amount(kind, status, amount) for kind, status, amount in rows)


def last_operation_at(db: Session, student_id: str) -> datetime | None:
    """Момент последней операции ученика в aware UTC; операций нет — None.

    Нужен сводке карточки ученика. Значение из SQLite приходит наивным
    (тип `DateTime(timezone=True)` tzinfo не сохраняет), поэтому
    нормализуется через `as_utc` — иначе сравнение с aware-временем
    упало бы на `TypeError`.
    """
    value = db.scalars(
        select(AccountOperation.occurred_at)
        .where(AccountOperation.student_id == student_id)
        .order_by(AccountOperation.occurred_at.desc())
        .limit(1)
    ).first()
    return as_utc(value) if value is not None else None
