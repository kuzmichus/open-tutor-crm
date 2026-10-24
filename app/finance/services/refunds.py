"""Возвраты по платежу: остаток к возврату и создание операции (design D5).

```
доступно к возврату = payment.amount − SUM(refund.amount WHERE payment_id = payment.id)
```

Правила (спека student-finance, «Возврат средств отдельной операцией»):

- возврат оформляется только по платежу в статусе «Оплачено»: «Ожидает»
  денег ещё не принёс, «Отменено» — уже нет, и возвращать нечего;
- сумма возврата больше нуля и не больше остатка: возвраты частичные и
  многократные, поэтому остаток считается, а не берётся из суммы платежа;
- возврат **не** меняет статус платежа: платёж остаётся «Оплачено», а в
  истории рядом появляется строка со знаком минус. Три статуса и кнопка
  «Возврат» не взаимозаменяемы (design D4).

`payment_id` связывает возврат с платежом; `status`/`method` у возврата
пустые — это держит `ck_account_operations_payment_fields`.

Сервис не знает про FastAPI: на вход — сессия, платёж и очищенные
значения, на выход — операция и список ошибок.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import (
    BALANCE_PAYMENT_STATUS,
    AccountOperation,
)
from app.finance.services.refund_form import validate_refund_data
from app.tutor.services.clock import utcnow

# Статус, при котором возврат допустим: деньги фактически получены.
REFUNDABLE_STATUS = BALANCE_PAYMENT_STATUS


def refunded_total(db: Session, payment_id: str) -> int:
    """Сколько уже возвращено по платежу (сумма всех возвратов).

    Один `SUM` вместо чтения строк: остаток нужен и диалогу, и проверке
    «не больше остатка», и повторять формулу в шаблоне нельзя — иначе
    кнопка «Полный возврат» подставила бы не то число.
    """
    total = db.scalar(
        select(func.coalesce(func.sum(AccountOperation.amount), 0)).where(
            AccountOperation.payment_id == payment_id,
            AccountOperation.kind == "refund",
        )
    )
    return int(total or 0)


def refund_totals_for_student(db: Session, student_id: str) -> dict[str, int]:
    """Возвраты ученика, сгруппированные по платежу: `{payment_id: сумма}`.

    Панель показывает остаток к возврату у каждого платежа, а платежей
    может быть много: по одному `SUM` на строку был бы N+1 на отрисовку
    вкладки. Один групповой запрос — та же формула, что у
    `refundable_amount`.
    """
    rows = db.execute(
        select(AccountOperation.payment_id, func.sum(AccountOperation.amount))
        .where(
            AccountOperation.student_id == student_id,
            AccountOperation.kind == "refund",
            AccountOperation.payment_id.is_not(None),
        )
        .group_by(AccountOperation.payment_id)
    ).all()
    return {payment_id: int(total or 0) for payment_id, total in rows}


def refundable_amount(db: Session, payment: AccountOperation) -> int:
    """Остаток к возврату; может быть нулём (всё уже вернули)."""
    return payment.amount - refunded_total(db, payment.id)


def validate_refund(
    db: Session, payment: AccountOperation, data: dict
) -> list[str]:
    """Правила возврата, требующие платежа и его истории возвратов.

    Сначала общие проверки данных (сумма, длина причины), затем статус
    платежа и остаток. Порядок важен для сообщений: при пустой сумме
    пользователь должен увидеть «Укажите сумму», а не «недопустимая
    операция».
    """
    errors = validate_refund_data(data)
    if errors:
        return errors

    if payment.status != REFUNDABLE_STATUS:
        return [
            "Возврат возможен только по платежу в статусе «Оплачено»: "
            "по этому платежу деньги ещё не получены."
        ]

    available = refundable_amount(db, payment)
    if data["amount"] > available:
        return [
            f"Сумма возврата больше доступной к возврату ({available} ₽)."
        ]
    return []


def create_refund(
    db: Session, payment: AccountOperation, data: dict
) -> tuple[AccountOperation | None, list[str]]:
    """Создаёт возврат по платежу; при ошибке ничего не сохраняет.

    Момент возврата — текущий момент (`occurred_at`), а не дата платежа:
    возврат происходит сегодня, и в истории он должен стоять там, где
    случился. Отдельного поля «дата возврата» в требованиях нет.
    """
    errors = validate_refund(db, payment, data)
    if errors:
        db.rollback()
        return None, errors

    refund = AccountOperation(
        student_id=payment.student_id,
        kind="refund",
        amount=data["amount"],
        occurred_at=utcnow(),
        comment=data.get("comment") or None,
        payment_id=payment.id,
    )
    db.add(refund)
    db.commit()
    return refund, []
