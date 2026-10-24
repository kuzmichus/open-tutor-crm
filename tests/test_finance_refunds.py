"""Тесты возвратов: остаток, правила, влияние на баланс.

Проверяются два уровня: разбор формы (`parse_refund_form`) и запись
(`create_refund`). Правила «только по оплаченному платежу» и «не больше
остатка» держатся в сервисе записи — форма их проверить не может, ей не
доступна история возвратов.
"""

from datetime import UTC, datetime

import pytest

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import balance
from app.finance.services.operations import payment_refunds, student_history
from app.finance.services.refund_form import parse_refund_form, validate_refund_data
from app.finance.services.refunds import (
    create_refund,
    refundable_amount,
    refunded_total,
)


def _payment(session, student_id: str, amount: int = 2400, status: str = "paid") -> AccountOperation:
    """Платёж напрямую в БД."""
    payment = AccountOperation(
        student_id=student_id,
        kind="payment",
        amount=amount,
        occurred_at=datetime(2026, 10, 22, 1, 31, tzinfo=UTC),
        status=status,
        method="card",
    )
    session.add(payment)
    session.commit()
    return payment


# --------------------------------------------------------------------------
# Разбор формы
# --------------------------------------------------------------------------


def test_refund_form_is_parsed():
    """Сумма числом, причина — как ввели."""
    data, errors = parse_refund_form({"amount": "500", "comment": "Отмена урока"})

    assert errors == []
    assert data["amount"] == 500
    assert data["comment"] == "Отмена урока"


def test_empty_refund_comment_becomes_none():
    """Пустая причина — отсутствие значения, а не пустая строка."""
    data, errors = parse_refund_form({"amount": "500", "comment": "  "})

    assert errors == []
    assert data["comment"] is None


@pytest.mark.parametrize("amount", ["0", "-100", "", "много"])
def test_refund_amount_must_be_positive_integer(amount):
    """Ноль, отрицательное, пустое и «много» возвратом не являются."""
    data, errors = parse_refund_form({"amount": amount})

    assert data["amount"] is None
    assert errors


def test_refund_amount_with_spaces_is_parsed():
    """«1 000» — та же тысяча."""
    data, errors = parse_refund_form({"amount": "1 000"})

    assert errors == []
    assert data["amount"] == 1000


def test_validate_refund_data_repeats_rules_without_form():
    """Правила держатся и без разбора формы (повтор в сервисе)."""
    errors = validate_refund_data({"amount": 0, "comment": "x" * 600})

    assert len(errors) == 2


# --------------------------------------------------------------------------
# Полный и частичные возвраты
# --------------------------------------------------------------------------


def test_full_refund_reduces_balance_to_zero(student_factory):
    """Полный возврат 2400 обнуляет баланс, платёж остаётся «Оплачено»."""
    student_id = student_factory()

    with SessionLocal() as session:
        payment = _payment(session, student_id, amount=2400)
        assert balance(session, student_id) == 2400

        refund, errors = create_refund(session, payment, {"amount": 2400, "comment": None})

        assert errors == []
        assert refund.kind == "refund"
        assert refund.amount == 2400
        assert refund.payment_id == payment.id
        assert refund.student_id == student_id
        # Возврат не трогает статус платежа (design D4).
        assert session.get(AccountOperation, payment.id).status == "paid"
        assert balance(session, student_id) == 0


def test_two_partial_refunds_leave_remainder(student_factory):
    """Два возврата по 1000 при платеже 2400 оставляют 400 к возврату."""
    student_id = student_factory()

    with SessionLocal() as session:
        payment = _payment(session, student_id, amount=2400)

        create_refund(session, payment, {"amount": 1000, "comment": None})
        create_refund(session, payment, {"amount": 1000, "comment": None})

        assert refunded_total(session, payment.id) == 2000
        assert refundable_amount(session, payment) == 400
        assert balance(session, student_id) == 400
        assert len(payment_refunds(session, payment.id)) == 2


def test_refund_exceeding_remainder_is_rejected(student_factory):
    """Возврат 1500 при остатке 1400 не создаётся и не меняет баланс."""
    student_id = student_factory()

    with SessionLocal() as session:
        payment = _payment(session, student_id, amount=2400)
        create_refund(session, payment, {"amount": 1000, "comment": None})

        refund, errors = create_refund(
            session, payment, {"amount": 1500, "comment": None}
        )

        assert refund is None
        assert any("1400" in message for message in errors)
        assert balance(session, student_id) == 1400
        assert len(payment_refunds(session, payment.id)) == 1


def test_refund_of_pending_payment_is_rejected(student_factory):
    """«Ожидает» — деньги не получены, возвращать нечего."""
    student_id = student_factory()

    with SessionLocal() as session:
        payment = _payment(session, student_id, amount=2400, status="pending")

        refund, errors = create_refund(
            session, payment, {"amount": 500, "comment": None}
        )

        assert refund is None
        assert any("Оплачено" in message for message in errors)
        assert balance(session, student_id) == 0


def test_refund_of_cancelled_payment_is_rejected(student_factory):
    """«Отменено» — платежа нет, возврат недопустим."""
    student_id = student_factory()

    with SessionLocal() as session:
        payment = _payment(session, student_id, amount=2400, status="cancelled")

        refund, errors = create_refund(
            session, payment, {"amount": 500, "comment": None}
        )

        assert refund is None
        assert errors


def test_refund_can_make_balance_negative(student_factory):
    """Ограничения «не ниже нуля» нет: возврат больше баланса даёт минус."""
    student_id = student_factory()

    with SessionLocal() as session:
        payment = _payment(session, student_id, amount=2400)
        # Урок 2000 списал часть денег — вернуть можно всё, баланс уйдёт в минус.
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="lesson",
                amount=2000,
                occurred_at=datetime(2026, 10, 23, 10, 0, tzinfo=UTC),
            )
        )
        session.commit()
        assert balance(session, student_id) == 400

        create_refund(session, payment, {"amount": 2400, "comment": None})

        assert balance(session, student_id) == -2000


def test_refund_appears_in_history(student_factory):
    """Возврат — отдельная строка истории со знаком минус."""
    student_id = student_factory()

    with SessionLocal() as session:
        payment = _payment(session, student_id, amount=2400)
        refund, _ = create_refund(session, payment, {"amount": 500, "comment": "Часть"})

        history = student_history(session, student_id)

    assert [row.id for row in history] == [refund.id, payment.id]


def test_refund_zero_amount_is_rejected_by_service(student_factory):
    """Правило «больше нуля» дублируется в сервисе записи."""
    student_id = student_factory()

    with SessionLocal() as session:
        payment = _payment(session, student_id, amount=2400)

        refund, errors = create_refund(session, payment, {"amount": 0, "comment": None})

        assert refund is None
        assert errors
        assert balance(session, student_id) == 2400
