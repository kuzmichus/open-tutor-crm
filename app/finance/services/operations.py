"""Выборки счёта: список платежей и история операций.

Два разных списка, и это не дублирование (спека student-finance, «Список
платежей отдельно от истории»):

- **платежи** — все строки `kind='payment'` при любом статусе, включая
  «Отменено»: репетитор должен видеть, что платёж был и что с ним стало,
  и иметь кнопки «Изменить»/«Возврат»;
- **история** — только операции, влияющие на баланс (оплаченные платежи,
  возвраты, списания за уроки). Отменённый платёж в историю не попадает,
  иначе сумма строк истории разошлась бы с балансом.

Оба списка сортируются по `occurred_at` по убыванию: у истории это
требование спеки, у платежей — тот же порядок, чтобы «свежий» платёж был
сверху. История ограничена последними 20 строками: пагинации в v1 нет
(design: Non-Goals), а страницу открывают ради проверки денег, а не
ради архива.

Сервис не знает про FastAPI и про шаблоны: возвращает ORM-строки, показ
форматирует `presentation.py`.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import (
    BALANCE_PAYMENT_STATUS,
    AccountOperation,
)
from app.finance.services.balance import DEBIT_KINDS

# Сколько последних операций показывает история (design: пагинации нет).
HISTORY_LIMIT = 20


def student_payments(db: Session, student_id: str) -> list[AccountOperation]:
    """Все платежи ученика в любом статусе, от новых к старым.

    Отменённый платёж здесь есть, в отличие от истории: статус виден
    подписью, а кнопки строки позволяют его исправить.
    """
    return list(
        db.scalars(
            select(AccountOperation)
            .where(
                AccountOperation.student_id == student_id,
                AccountOperation.kind == "payment",
            )
            .order_by(
                AccountOperation.occurred_at.desc(),
                AccountOperation.created_at.desc(),
            )
        ).all()
    )


def student_history(
    db: Session, student_id: str, *, limit: int = HISTORY_LIMIT
) -> list[AccountOperation]:
    """Операции, влияющие на баланс, от новых к старым (не больше `limit`).

    Условие «влияет на баланс» повторяет правило `balance.affects_balance`
    в SQL: платёж — только `paid`, возвраты и списания — всегда. Сортировка
    вторичным ключом `created_at` нужна для операций с одинаковым
    `occurred_at` (два платежа одной датой): без него порядок строк был бы
    произвольным и «первая строка» в тесте могла бы меняться.
    """
    return list(
        db.scalars(
            select(AccountOperation)
            .where(
                AccountOperation.student_id == student_id,
                (
                    (
                        (AccountOperation.kind == "payment")
                        & (AccountOperation.status == BALANCE_PAYMENT_STATUS)
                    )
                    | AccountOperation.kind.in_(DEBIT_KINDS)
                ),
            )
            .order_by(
                AccountOperation.occurred_at.desc(),
                AccountOperation.created_at.desc(),
            )
            .limit(limit)
        ).all()
    )


def payment_refunds(db: Session, payment_id: str) -> list[AccountOperation]:
    """Возвраты по платежу, от новых к старым."""
    return list(
        db.scalars(
            select(AccountOperation)
            .where(
                AccountOperation.payment_id == payment_id,
                AccountOperation.kind == "refund",
            )
            .order_by(
                AccountOperation.occurred_at.desc(),
                AccountOperation.created_at.desc(),
            )
        ).all()
    )
