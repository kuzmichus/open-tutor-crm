"""Тесты отображения счёта: деньги, знак, подписи, дата в зоне педагога.

Проверяется только формат: суммы и знаки, подписи закрытых списков и
перевод времени в зону педагога. Бизнес-правила (что входит в баланс)
живут в `balance.py` и проверяются отдельно.
"""

from datetime import UTC, datetime

import pytest

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.presentation import (
    MINUS,
    balance_label,
    money,
    operation_datetime,
    operation_kind_label,
    payment_method_label,
    payment_status_label,
    signed_money,
)
from app.tutor.models.tutor import Tutor

NBSP = "\u00a0"


def _tutor(db, timezone: str = "UTC") -> Tutor:
    """Репетитор с нужной зоной: читается из БД, как во вьюхах."""
    tutor = Tutor(
        name="Педагог",
        email=f"presentation-{timezone.replace('/', '-')}@example.com",
        timezone=timezone,
    )
    db.add(tutor)
    db.commit()
    return tutor


def _operation(db, student_id: str, **values) -> AccountOperation:
    """Операция счёта с разумными значениями по умолчанию."""
    defaults = {
        "student_id": student_id,
        "kind": "payment",
        "amount": 2000,
        "occurred_at": datetime(2026, 10, 22, 1, 31, tzinfo=UTC),
        "status": "paid",
        "method": "transfer",
    }
    defaults.update(values)
    operation = AccountOperation(**defaults)
    db.add(operation)
    db.commit()
    return operation


# --------------------------------------------------------------------------
# Деньги
# --------------------------------------------------------------------------


def test_money_uses_non_breaking_spaces():
    """«1 200 ₽»: разряды и знак рубля не разрываются переносом строки."""
    assert money(1200) == f"1{NBSP}200{NBSP}₽"
    assert money(10_800) == f"10{NBSP}800{NBSP}₽"


def test_money_of_zero_and_none():
    """Ноль — это «0 ₽», а отсутствие значения — пустая строка."""
    assert money(0) == f"0{NBSP}₽"
    assert money(None) == ""


def test_balance_label_marks_only_debt():
    """Баланс: «800 ₽» без плюса, «0 ₽», «−200 ₽» с типографским минусом."""
    assert balance_label(800) == f"800{NBSP}₽"
    assert balance_label(0) == f"0{NBSP}₽"
    assert balance_label(-200) == f"{MINUS}200{NBSP}₽"


def test_minus_is_typographic():
    """Минус — U+2212, а не дефис-минус (как на референсе)."""
    assert MINUS == "\u2212"
    assert "-" not in balance_label(-200)


def test_signed_money_marks_payment_positive(student_factory):
    """Платёж в истории — «+2 000 ₽»."""
    student_id = student_factory()

    with SessionLocal() as session:
        operation = _operation(session, student_id, amount=2000)

    assert signed_money(operation) == f"+2{NBSP}000{NBSP}₽"


@pytest.mark.parametrize("kind", ["refund", "lesson"])
def test_signed_money_marks_debits_negative(student_factory, kind):
    """Возврат и списание — со знаком минус."""
    student_id = student_factory()

    with SessionLocal() as session:
        operation = _operation(
            session,
            student_id,
            kind=kind,
            amount=1200,
            status=None,
            method=None,
        )

    assert signed_money(operation) == f"{MINUS}1{NBSP}200{NBSP}₽"


def test_signed_money_of_pending_payment_has_no_amount(student_factory):
    """Неоплаченный платёж не влияет на баланс, значит и вклада не имеет.

    В историю такие операции не попадают (`operations.student_history`),
    но функция обязана остаться согласованной с формулой баланса: сумма
    вклада — ноль.
    """
    student_id = student_factory()

    with SessionLocal() as session:
        operation = _operation(session, student_id, status="pending")

    assert signed_money(operation) == f"+0{NBSP}₽"


# --------------------------------------------------------------------------
# Подписи
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "label"),
    [("transfer", "Перевод"), ("card", "Карта"), ("online", "Онлайн")],
)
def test_payment_kind_label_is_method(student_factory, method, label):
    """В истории платёж подписан способом: «Перевод», «Карта», «Онлайн»."""
    student_id = student_factory()

    with SessionLocal() as session:
        operation = _operation(session, student_id, method=method)

    assert operation_kind_label(operation) == label


def test_payment_without_method_has_neutral_label(student_factory):
    """Способ не задан — нейтральное «Платёж», а не пустая строка."""
    student_id = student_factory()

    with SessionLocal() as session:
        operation = _operation(session, student_id, method=None)

    assert operation_kind_label(operation) == "Платёж"


@pytest.mark.parametrize(
    ("kind", "label"),
    [("refund", "Возврат средств"), ("lesson", "Урок")],
)
def test_debit_kind_labels(student_factory, kind, label):
    """Возврат и списание подписаны своими видами."""
    student_id = student_factory()

    with SessionLocal() as session:
        operation = _operation(
            session, student_id, kind=kind, status=None, method=None
        )

    assert operation_kind_label(operation) == label


@pytest.mark.parametrize(
    ("status", "label"),
    [("paid", "Оплачено"), ("pending", "Ожидает"), ("cancelled", "Отменено")],
)
def test_payment_status_labels(status, label):
    """Статусы платежа — русские подписи из закрытого списка модели."""
    assert payment_status_label(status) == label


def test_payment_status_and_method_labels_of_empty_value():
    """Пустое значение подписи не придумывает: возвращается пустая строка."""
    assert payment_status_label(None) == ""
    assert payment_method_label(None) == ""


# --------------------------------------------------------------------------
# Дата и время
# --------------------------------------------------------------------------


def test_operation_datetime_format_in_utc():
    """«22 окт. 2026, 01:31» — формат из design D15."""
    with SessionLocal() as session:
        tutor = _tutor(session, "UTC")

    assert operation_datetime(
        datetime(2026, 10, 22, 1, 31, tzinfo=UTC), tutor
    ) == "22 окт. 2026, 01:31"


def test_operation_datetime_uses_tutor_zone():
    """В зоне педагога UTC+04 момент сдвигается: 01:31 UTC → 05:31."""
    with SessionLocal() as session:
        tutor = _tutor(session, "Asia/Dubai")  # UTC+04 круглый год

    assert operation_datetime(
        datetime(2026, 10, 22, 1, 31, tzinfo=UTC), tutor
    ) == "22 окт. 2026, 05:31"


def test_operation_datetime_shifts_day_across_zone():
    """Сдвиг может перевести дату на следующий день — показывается она же."""
    with SessionLocal() as session:
        tutor = _tutor(session, "Asia/Dubai")

    assert operation_datetime(
        datetime(2026, 10, 21, 22, 15, tzinfo=UTC), tutor
    ) == "22 окт. 2026, 02:15"


def test_operation_datetime_of_naive_value_from_sqlite(student_factory):
    """Naive-значение из SQLite трактуется как UTC, а не как время педагога."""
    with SessionLocal() as session:
        tutor = _tutor(session, "Asia/Dubai")
        operation_id = _operation(session, student_factory()).id

    # Значение читается в новой сессии: после commit объект в исходной
    # сессии сохраняет aware-значение, а из БД оно приходит наивным.
    with SessionLocal() as session:
        value = session.get(AccountOperation, operation_id).occurred_at
    assert value.tzinfo is None

    assert operation_datetime(value, tutor) == "22 окт. 2026, 05:31"


def test_operation_datetime_of_none_is_empty():
    """Нет значения — пустая строка, а не «None» в разметке."""
    with SessionLocal() as session:
        tutor = _tutor(session)

    assert operation_datetime(None, tutor) == ""


def test_helpers_are_registered_in_jinja():
    """Хелперы доступны шаблонам без импорта во вьюхах."""
    from app.templating import templates

    for name in (
        "money",
        "signed_money",
        "balance_label",
        "operation_kind_label",
        "payment_status_label",
        "payment_method_label",
        "operation_datetime",
    ):
        assert name in templates.env.globals, f"хелпер {name} не зарегистрирован"
