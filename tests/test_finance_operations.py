"""Тесты выборок счёта: платежи, история, порядок и лимит.

Главная проверка — два списка расходятся там, где должны: отменённый
платёж есть в списке платежей и отсутствует в истории, потому что баланс
он не меняет (спека student-finance, «Список платежей отдельно от
истории»).
"""

from datetime import UTC, datetime

from app.database import SessionLocal
from app.finance.services.operations import (
    HISTORY_LIMIT,
    payment_refunds,
    student_history,
    student_payments,
)


def _at(day: int, hour: int = 10) -> datetime:
    """Момент операции: октябрь 2026, чтобы порядок был очевиден."""
    return datetime(2026, 10, day, hour, 0, tzinfo=UTC)


def test_payments_include_cancelled_and_pending(student_factory, operation_factory):
    """Список платежей полон: три статуса видны все."""
    student_id = student_factory()
    paid = operation_factory(student_id=student_id, amount=2000, status="paid")
    pending = operation_factory(student_id=student_id, amount=2400, status="pending")
    cancelled = operation_factory(
        student_id=student_id, amount=1000, status="cancelled"
    )

    with SessionLocal() as session:
        payments = student_payments(session, student_id)

    assert {payment.id for payment in payments} == {paid, pending, cancelled}


def test_history_excludes_cancelled_payment(student_factory, operation_factory):
    """Отменённый платёж виден в платежах, но не в истории."""
    student_id = student_factory()
    paid = operation_factory(student_id=student_id, amount=2000, status="paid")
    cancelled = operation_factory(
        student_id=student_id, amount=1000, status="cancelled"
    )

    with SessionLocal() as session:
        payments = student_payments(session, student_id)
        history = student_history(session, student_id)

    assert {payment.id for payment in payments} == {paid, cancelled}
    assert [operation.id for operation in history] == [paid]


def test_history_excludes_pending_payment(student_factory, operation_factory):
    """«Ожидает» тоже не влияет на баланс и в историю не попадает."""
    student_id = student_factory()
    pending = operation_factory(student_id=student_id, amount=2400, status="pending")

    with SessionLocal() as session:
        assert [op.id for op in student_history(session, student_id)] == []
        assert [p.id for p in student_payments(session, student_id)] == [pending]


def test_history_contains_refunds_and_charges(student_factory, operation_factory):
    """История — оплаченные платежи, возвраты и списания за уроки."""
    student_id = student_factory()
    payment = operation_factory(
        student_id=student_id, amount=2000, occurred_at=_at(14)
    )
    charge = operation_factory(
        student_id=student_id, kind="lesson", amount=1200, occurred_at=_at(16)
    )
    refund = operation_factory(
        student_id=student_id, kind="refund", amount=500, occurred_at=_at(21)
    )

    with SessionLocal() as session:
        history = student_history(session, student_id)

    assert {operation.id for operation in history} == {payment, charge, refund}


def test_history_is_ordered_newest_first(student_factory, operation_factory):
    """Операции на 14, 16 и 21 октября идут от 21-го к 14-му (сценарий спеки)."""
    student_id = student_factory()
    operation_factory(student_id=student_id, amount=2000, occurred_at=_at(14))
    operation_factory(
        student_id=student_id, kind="lesson", amount=1200, occurred_at=_at(16)
    )
    operation_factory(
        student_id=student_id, kind="refund", amount=500, occurred_at=_at(21)
    )

    with SessionLocal() as session:
        history = student_history(session, student_id)

    assert [op.occurred_at.day for op in history] == [21, 16, 14]


def test_payments_are_ordered_newest_first(student_factory, operation_factory):
    """Список платежей — в том же порядке: свежий сверху."""
    student_id = student_factory()
    operation_factory(student_id=student_id, amount=1000, occurred_at=_at(14))
    operation_factory(student_id=student_id, amount=2000, occurred_at=_at(21))

    with SessionLocal() as session:
        payments = student_payments(session, student_id)

    assert [payment.occurred_at.day for payment in payments] == [21, 14]


def test_history_is_limited_to_last_operations(student_factory, operation_factory):
    """История показывает не больше `HISTORY_LIMIT` строк — самые новые."""
    student_id = student_factory()
    for index in range(HISTORY_LIMIT + 5):
        operation_factory(
            student_id=student_id,
            amount=1000 + index,
            # Даты идут подряд по дням: часов в сутках меньше, чем операций.
            occurred_at=_at(1 + index),
        )

    with SessionLocal() as session:
        history = student_history(session, student_id)

    assert len(history) == HISTORY_LIMIT
    # Отрезаны самые старые, а не самые новые.
    assert history[0].amount == 1000 + HISTORY_LIMIT + 4
    assert min(op.amount for op in history) == 1005


def test_history_and_payments_are_scoped_to_one_student(
    tutor_factory, student_factory, operation_factory
):
    """Чужие операции в выборки не попадают."""
    tutor_id = tutor_factory()
    first = student_factory(tutor_id=tutor_id)
    second = student_factory(tutor_id=tutor_id)
    own = operation_factory(student_id=first, amount=2000)
    operation_factory(student_id=second, amount=9000)

    with SessionLocal() as session:
        assert [p.id for p in student_payments(session, first)] == [own]
        assert [op.id for op in student_history(session, first)] == [own]


def test_payment_refunds_lists_only_its_refunds(student_factory, operation_factory):
    """Возвраты платежа: только его собственные, от новых к старым."""
    student_id = student_factory()
    payment = operation_factory(student_id=student_id, amount=2400)
    other = operation_factory(student_id=student_id, amount=1000)
    first = operation_factory(
        student_id=student_id,
        kind="refund",
        amount=1000,
        payment_id=payment,
        occurred_at=_at(20),
    )
    second = operation_factory(
        student_id=student_id,
        kind="refund",
        amount=400,
        payment_id=payment,
        occurred_at=_at(22),
    )
    operation_factory(
        student_id=student_id,
        kind="refund",
        amount=100,
        payment_id=other,
        occurred_at=_at(23),
    )

    with SessionLocal() as session:
        refunds = payment_refunds(session, payment)

    assert [refund.id for refund in refunds] == [second, first]
