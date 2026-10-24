"""Тесты формы и записи платежа: разбор, валидация, влияние на баланс.

Проверяются два уровня: разбор HTTP-формы (`parse_payment_form`) и запись
(`create_payment`/`update_payment`). Второй не доверяет первому — правила
дублируются, и тесты это фиксируют.
"""

from datetime import date, datetime

import pytest

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import balance
from app.finance.services.payment_form import (
    empty_payment_form,
    parse_payment_form,
    payment_to_form,
    validate_payment_data,
)
from app.finance.services.payment_writer import create_payment, update_payment
from app.tutor.models.tutor import Tutor


def _tutor(db, timezone: str = "UTC") -> Tutor:
    tutor = Tutor(
        name="Педагог",
        email=f"payments-{timezone.replace('/', '-')}-{db.bind.url.database}@example.com",
        timezone=timezone,
    )
    db.add(tutor)
    db.commit()
    return tutor


def _form(**overrides) -> dict:
    """Поля формы платежа; `None` в значении — поля нет вовсе."""
    values = {
        "amount": "2000",
        "method": "transfer",
        "status": "paid",
        "date": "2026-10-22",
        "comment": "",
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not None}


# --------------------------------------------------------------------------
# Разбор формы
# --------------------------------------------------------------------------


def test_valid_form_is_parsed():
    """Корректная форма: сумма числом, способ, статус и дата."""
    data, errors = parse_payment_form(_form(comment="За октябрь"))

    assert errors == []
    assert data["amount"] == 2000
    assert data["method"] == "transfer"
    assert data["status"] == "paid"
    assert data["date"] == date(2026, 10, 22)
    assert data["comment"] == "За октябрь"


def test_empty_comment_becomes_none():
    """Пустой комментарий — это отсутствие значения, а не пустая строка."""
    data, errors = parse_payment_form(_form(comment=""))

    assert errors == []
    assert data["comment"] is None


@pytest.mark.parametrize("amount", ["0", "-100", ""])
def test_non_positive_or_empty_amount_is_an_error(amount):
    """Ноль, отрицательная сумма и пустое поле отклоняются (сценарий спеки)."""
    data, errors = parse_payment_form(_form(amount=amount))

    assert data["amount"] is None
    assert errors


def test_non_numeric_amount_is_an_error():
    """«много» суммой не является."""
    data, errors = parse_payment_form(_form(amount="много"))

    assert data["amount"] is None
    assert any("целое" in message for message in errors)


def test_amount_with_spaces_is_parsed():
    """«1 200» — та же тысяча двести: пробелы в числе не ошибка."""
    data, errors = parse_payment_form(_form(amount="1 200"))

    assert errors == []
    assert data["amount"] == 1200


@pytest.mark.parametrize("field", ["method", "status"])
def test_unknown_choice_is_an_error(field):
    """Способ и статус — только из закрытых списков модели."""
    data, errors = parse_payment_form(_form(**{field: "unknown"}))

    assert data[field] is None
    assert errors


@pytest.mark.parametrize("raw", ["", "22.10.2026", "не дата"])
def test_date_is_required_and_validated(raw):
    """Дата обязательна и разбирается только как ISO."""
    data, errors = parse_payment_form(_form(date=raw))

    assert data["date"] is None
    assert errors


def test_validate_payment_data_repeats_rules_without_form():
    """Правила держатся и без разбора формы (повтор в writer'е)."""
    errors = validate_payment_data(
        {
            "amount": 0,
            "method": "crypto",
            "status": "done",
            "date": None,
        }
    )

    assert len(errors) == 4


def test_empty_form_defaults_to_paid_transfer():
    """Пустая форма: «Оплачено», «Перевод» и переданная дата."""
    form = empty_payment_form(date(2026, 11, 1))

    assert form["amount"] == ""
    assert form["method"] == "transfer"
    assert form["status"] == "paid"
    assert form["date_value"] == "2026-11-01"


def test_payment_to_form_shows_date_in_tutor_zone():
    """Дата правки — тот день, в который платёж был внесён (зона педагога)."""
    with SessionLocal() as session:
        tutor = _tutor(session, "Asia/Dubai")
        payment = AccountOperation(
            student_id="ignored-for-rendering",
            kind="payment",
            amount=2400,
            # 21.10 22:15 UTC — это уже 22.10 02:15 в UTC+04.
            occurred_at=datetime(2026, 10, 21, 22, 15),
            status="paid",
            method="card",
        )

        form = payment_to_form(payment, tutor)

    assert form["amount"] == "2400"
    assert form["method"] == "card"
    assert form["status"] == "paid"
    assert form["date_value"] == "2026-10-22"


# --------------------------------------------------------------------------
# Создание платежа
# --------------------------------------------------------------------------


def test_create_payment_appears_in_balance(student_factory):
    """Платёж 2000 со статусом «Оплачено» сразу входит в баланс."""
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        payment, errors = create_payment(
            session,
            student_id,
            {
                "amount": 2000,
                "method": "transfer",
                "status": "paid",
                "date": date(2026, 10, 22),
                "comment": "За октябрь",
            },
            tutor,
        )

        assert errors == []
        assert payment.student_id == student_id
        assert payment.kind == "payment"
        assert payment.amount == 2000
        assert payment.status == "paid"
        assert payment.method == "transfer"
        assert payment.comment == "За октябрь"
        assert balance(session, student_id) == 2000


def test_create_payment_rejects_non_positive_amount(student_factory):
    """Неположительная сумма не создаёт платёж (сценарий спеки)."""
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        payment, errors = create_payment(
            session,
            student_id,
            {
                "amount": 0,
                "method": "transfer",
                "status": "paid",
                "date": date(2026, 10, 22),
            },
            tutor,
        )

        assert payment is None
        assert errors
        assert session.query(AccountOperation).all() == []
        assert balance(session, student_id) == 0


def test_pending_payment_does_not_change_balance(student_factory):
    """«Ожидает» создаётся, но баланс не меняет (сценарий спеки)."""
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        create_payment(
            session,
            student_id,
            {
                "amount": 2400,
                "method": "card",
                "status": "pending",
                "date": date(2026, 10, 22),
            },
            tutor,
        )

        assert balance(session, student_id) == 0


def test_payment_time_comes_from_moment_of_saving(student_factory):
    """Время операции — текущее время педагога, дата — из формы (design D15)."""
    from app.common.services.tutor_time import now_local, to_local

    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session, "Asia/Dubai")
        before = now_local(tutor).replace(second=0, microsecond=0)
        payment, _ = create_payment(
            session,
            student_id,
            {
                "amount": 1000,
                "method": "online",
                "status": "paid",
                "date": date(2026, 10, 22),
            },
            tutor,
        )
        local = to_local(payment.occurred_at, tutor)
        after = now_local(tutor).replace(second=0, microsecond=0)

    # Дата — из формы, а не «сегодня».
    assert local.date() == date(2026, 10, 22)
    # Время суток — момент сохранения (с точностью до минуты), а не полночь.
    assert local.second == 0
    assert before.time() <= local.time() <= after.time()


# --------------------------------------------------------------------------
# Правка платежа
# --------------------------------------------------------------------------


def _payment(session, student_id: str, amount: int = 2400, **extra) -> str:
    """Оплаченный платёж в БД; возвращает id."""
    values = {
        "student_id": student_id,
        "kind": "payment",
        "amount": amount,
        "occurred_at": datetime(2026, 10, 22, 1, 31),
        "status": "paid",
        "method": "card",
    }
    values.update(extra)
    payment = AccountOperation(**values)
    session.add(payment)
    session.commit()
    return payment.id


def test_update_amount_changes_balance(student_factory):
    """Правка суммы 2400 → 2000 уменьшает баланс на 400 (сценарий спеки)."""
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        payment_id = _payment(session, student_id, amount=2400)
        assert balance(session, student_id) == 2400

        errors = update_payment(
            session,
            session.get(AccountOperation, payment_id),
            {
                "amount": 2000,
                "method": "card",
                "status": "paid",
                "date": date(2026, 10, 22),
                "comment": None,
            },
            tutor,
        )

        assert errors == []
        assert session.get(AccountOperation, payment_id).amount == 2000
        assert balance(session, student_id) == 2000


def test_update_keeps_occurred_at_when_date_is_unchanged(student_factory):
    """Правка комментария не переставляет операцию в истории."""
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        payment_id = _payment(session, student_id)
        before = session.get(AccountOperation, payment_id).occurred_at

        update_payment(
            session,
            session.get(AccountOperation, payment_id),
            {
                "amount": 2400,
                "method": "card",
                "status": "paid",
                "date": date(2026, 10, 22),
                "comment": "Уточнён комментарий",
            },
            tutor,
        )

        assert session.get(AccountOperation, payment_id).occurred_at == before


def test_update_moves_occurred_at_when_date_changes(student_factory):
    """Перенос даты меняет момент операции: история следует за датой."""
    from app.common.services.tutor_time import to_local

    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session, "Asia/Dubai")
        payment_id = _payment(session, student_id)

        update_payment(
            session,
            session.get(AccountOperation, payment_id),
            {
                "amount": 2400,
                "method": "card",
                "status": "paid",
                "date": date(2026, 10, 25),
                "comment": None,
            },
            tutor,
        )

        local = to_local(session.get(AccountOperation, payment_id).occurred_at, tutor)

    assert local.date() == date(2026, 10, 25)


def test_update_status_to_paid_adds_to_balance(student_factory):
    """«Ожидает» → «Оплачено» увеличивает баланс на сумму (сценарий спеки)."""
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        payment_id = _payment(session, student_id, amount=2400, status="pending")
        assert balance(session, student_id) == 0

        update_payment(
            session,
            session.get(AccountOperation, payment_id),
            {
                "amount": 2400,
                "method": "card",
                "status": "paid",
                "date": date(2026, 10, 22),
                "comment": None,
            },
            tutor,
        )

        assert balance(session, student_id) == 2400


def test_update_rejects_cancel_when_payment_has_refund(student_factory):
    """Отмена платежа с возвратом отклоняется: история уже вернула деньги."""
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        payment_id = _payment(session, student_id, amount=2000)
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="refund",
                amount=500,
                occurred_at=datetime(2026, 10, 22, 2, 0),
                payment_id=payment_id,
                comment="Возврат части",
            )
        )
        session.commit()

        errors = update_payment(
            session,
            session.get(AccountOperation, payment_id),
            {
                "amount": 2000,
                "method": "card",
                "status": "cancelled",
                "date": date(2026, 10, 22),
                "comment": None,
            },
            tutor,
        )

        assert any("возврат" in message.lower() for message in errors)
        assert session.get(AccountOperation, payment_id).status == "paid"
        # Возврат по-прежнему учтён: баланс не откатился вместе с отменой.
        assert balance(session, student_id) == 1500


def test_update_allows_cancel_without_refunds(student_factory):
    """Без возвратов отмена разрешена и выводит сумму из баланса."""
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        payment_id = _payment(session, student_id, amount=2000)

        errors = update_payment(
            session,
            session.get(AccountOperation, payment_id),
            {
                "amount": 2000,
                "method": "card",
                "status": "cancelled",
                "date": date(2026, 10, 22),
                "comment": None,
            },
            tutor,
        )

        assert errors == []
        assert session.get(AccountOperation, payment_id).status == "cancelled"
        assert balance(session, student_id) == 0


def test_update_keeps_cancelled_payment_cancellable(student_factory):
    """Уже отменённый платёж с возвратом можно править дальше.

    Запрет касается только перехода в «Отменено»: возврат мог появиться
    после отмены (так история и остаётся непротиворечивой), и правка
    комментария не должна упираться в ту же проверку.
    """
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        payment_id = _payment(session, student_id, amount=2000, status="cancelled")
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="refund",
                amount=500,
                occurred_at=datetime(2026, 10, 22, 2, 0),
                payment_id=payment_id,
            )
        )
        session.commit()

        errors = update_payment(
            session,
            session.get(AccountOperation, payment_id),
            {
                "amount": 2000,
                "method": "card",
                "status": "cancelled",
                "date": date(2026, 10, 22),
                "comment": "Уточнение",
            },
            tutor,
        )

        assert errors == []
        assert session.get(AccountOperation, payment_id).comment == "Уточнение"


def test_update_rejects_invalid_data(student_factory):
    """Невалидная правка не меняет запись."""
    student_id = student_factory()

    with SessionLocal() as session:
        tutor = _tutor(session)
        payment_id = _payment(session, student_id, amount=2400)

        errors = update_payment(
            session,
            session.get(AccountOperation, payment_id),
            {
                "amount": -5,
                "method": "crypto",
                "status": "paid",
                "date": date(2026, 10, 22),
                "comment": None,
            },
            tutor,
        )

        assert errors
        assert session.get(AccountOperation, payment_id).amount == 2400
