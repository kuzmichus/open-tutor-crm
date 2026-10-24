"""Тесты формулы баланса (design D3).

Баланс — производная сумма со знаком: оплаченные платежи минус возвраты и
списания. Проверяем ровно те случаи, которые спека называет сценариями:
положительный баланс, отрицательный после возврата, ноль без операций,
неоплаченные платежи не учитываются.
"""

from datetime import UTC, datetime, timedelta

from app.database import SessionLocal
from app.finance.services.balance import (
    affects_balance,
    balance,
    last_operation_at,
    signed_amount,
)


def test_balance_is_zero_without_operations(student_factory):
    """Ученик без операций: баланс 0, а не «нет данных»."""
    student_id = student_factory()

    with SessionLocal() as session:
        assert balance(session, student_id) == 0


def test_paid_payment_minus_charge(student_factory, operation_factory):
    """Платёж 2000 и списание 1200 дают баланс 800 (сценарий спеки)."""
    student_id = student_factory()
    operation_factory(student_id=student_id, kind="payment", amount=2000)
    operation_factory(student_id=student_id, kind="lesson", amount=1200)

    with SessionLocal() as session:
        assert balance(session, student_id) == 800


def test_balance_goes_negative_after_refund(student_factory, operation_factory):
    """Возврат больше остатка даёт отрицательный баланс без обрезки нулём."""
    student_id = student_factory()
    operation_factory(student_id=student_id, kind="payment", amount=2000)
    operation_factory(student_id=student_id, kind="lesson", amount=1200)
    operation_factory(student_id=student_id, kind="refund", amount=500)

    with SessionLocal() as session:
        # 2000 − 1200 − 500 = 300; теперь возврат больше остатка.
        assert balance(session, student_id) == 300

    operation_factory(student_id=student_id, kind="refund", amount=500)

    with SessionLocal() as session:
        assert balance(session, student_id) == -200


def test_pending_payment_is_not_counted(student_factory, operation_factory):
    """«Ожидает» виден в списке платежей, но баланс не меняет."""
    student_id = student_factory()
    operation_factory(
        student_id=student_id, kind="payment", amount=2400, status="pending"
    )

    with SessionLocal() as session:
        assert balance(session, student_id) == 0


def test_cancelled_payment_is_not_counted(student_factory, operation_factory):
    """«Отменено» не входит в баланс."""
    student_id = student_factory()
    operation_factory(
        student_id=student_id, kind="payment", amount=2400, status="cancelled"
    )

    with SessionLocal() as session:
        assert balance(session, student_id) == 0


def test_payment_becomes_counted_when_status_turns_paid(
    student_factory, operation_factory
):
    """Смена статуса на «Оплачено» добавляет сумму к балансу.

    Баланс производный: менять его отдельно не нужно и негде.
    """
    from app.finance.models.account_operation import AccountOperation

    student_id = student_factory()
    operation_id = operation_factory(
        student_id=student_id, kind="payment", amount=2400, status="pending"
    )

    with SessionLocal() as session:
        assert balance(session, student_id) == 0
        session.get(AccountOperation, operation_id).status = "paid"
        session.commit()

    with SessionLocal() as session:
        assert balance(session, student_id) == 2400


def test_balance_is_scoped_to_one_student(
    tutor_factory, student_factory, operation_factory
):
    """Операции другого ученика того же репетитора в баланс не попадают."""
    tutor_id = tutor_factory()
    first = student_factory(tutor_id=tutor_id)
    second = student_factory(tutor_id=tutor_id)
    operation_factory(student_id=first, kind="payment", amount=2000)
    operation_factory(student_id=second, kind="payment", amount=9000)

    with SessionLocal() as session:
        assert balance(session, first) == 2000
        assert balance(session, second) == 9000


def test_signed_amount_matches_kind():
    """Знак вклада выводится из вида: платёж «+», возврат и урок «−»."""
    assert signed_amount("payment", "paid", 2000) == 2000
    assert signed_amount("refund", None, 500) == -500
    assert signed_amount("lesson", None, 1200) == -1200
    # Неоплаченный платёж не даёт вклада вовсе.
    assert signed_amount("payment", "pending", 2400) == 0
    assert signed_amount("payment", "cancelled", 2400) == 0


def test_affects_balance_rule():
    """В баланс входят оплаченные платежи, возвраты и списания."""
    assert affects_balance("payment", "paid") is True
    assert affects_balance("payment", "pending") is False
    assert affects_balance("payment", "cancelled") is False
    assert affects_balance("refund", None) is True
    assert affects_balance("lesson", None) is True


def test_last_operation_at_is_aware_utc(student_factory, operation_factory):
    """Последняя операция возвращается aware-значением, а не naive из SQLite."""
    student_id = student_factory()
    operation_factory(
        student_id=student_id,
        kind="payment",
        amount=1000,
        occurred_at=datetime(2026, 10, 14, 9, 0, tzinfo=UTC),
    )
    operation_factory(
        student_id=student_id,
        kind="payment",
        amount=2000,
        occurred_at=datetime(2026, 10, 21, 9, 0, tzinfo=UTC),
    )

    with SessionLocal() as session:
        value = last_operation_at(session, student_id)

    assert value.tzinfo is not None
    assert value == datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
    # Значение сравнимо с aware-«сейчас» — это и есть смысл нормализации.
    assert value < datetime.now(UTC) + timedelta(days=1)


def test_last_operation_at_is_none_without_operations(student_factory):
    """Ученик без операций: момента операции нет (None, а не исключение)."""
    student_id = student_factory()

    with SessionLocal() as session:
        assert last_operation_at(session, student_id) is None
