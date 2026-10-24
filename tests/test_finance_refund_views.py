"""Тесты диалога возврата: маршруты, ответы и разметка формы.

Проверяется поведение через HTTP: диалог показывает сумму платежа и
остаток, возврат не меняет статус платежа, ошибки возвращаются тем же
фрагментом, успех — закрытием диалога с `payment-saved`.
"""

import re

import pytest

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import balance

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="refund-owner@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "refund-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def student_id(student_factory, owner):
    """Ученик вошедшего репетитора."""
    return student_factory(tutor_id=owner, first_name="Мария", last_name="Петрова")


def _payment(student_id: str, amount: int = 2400, status: str = "paid") -> str:
    """Платёж напрямую в БД; возвращает его id."""
    from datetime import UTC, datetime

    with SessionLocal() as session:
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
        return payment.id


# --------------------------------------------------------------------------
# Разметка диалога
# --------------------------------------------------------------------------


def test_refund_dialog_shows_payment_amount_and_remainder(client, student_id):
    """Диалог показывает сумму платежа и доступно к возврату."""
    payment_id = _payment(student_id, amount=2400)

    response = client.get(f"/tutor/payments/{payment_id}/refund/new")

    assert response.status_code == 200
    html = response.text
    assert "Оформить возврат" in html
    # «2 400 ₽» с неразрывными пробелами — форматтер `money`.
    assert "2\u00a0400\u00a0₽" in html
    assert "Доступно к возврату" in html


def test_refund_dialog_remainder_after_partial_refund(client, student_id):
    """Остаток учитывает уже оформленный возврат: 2400 − 1000 = 1400."""
    from datetime import UTC, datetime

    payment_id = _payment(student_id, amount=2400)
    with SessionLocal() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="refund",
                amount=1000,
                occurred_at=datetime(2026, 10, 23, 10, 0, tzinfo=UTC),
                payment_id=payment_id,
            )
        )
        session.commit()

    html = client.get(f"/tutor/payments/{payment_id}/refund/new").text

    assert "1\u00a0400\u00a0₽" in html


def test_full_refund_button_does_not_send_request(client, student_id):
    """Кнопка «Полный возврат» не содержит `hx-*` и не отправляет запрос."""
    payment_id = _payment(student_id, amount=2400)

    html = client.get(f"/tutor/payments/{payment_id}/refund/new").text

    start = html.index("Полный возврат")
    # Атрибуты кнопки — всё, что стоит перед её текстом в том же теге.
    tag_start = html.rindex("<button", 0, start)
    tag = html[tag_start : html.index(">", start) + 1]
    assert "hx-" not in tag
    assert 'type="submit"' not in tag
    assert 'type="button"' in tag


def test_refund_form_sends_only_its_fields(client, student_id):
    """В запрос уходят только сумма и причина."""
    payment_id = _payment(student_id)

    html = client.get(f"/tutor/payments/{payment_id}/refund/new").text

    names = set(re.findall(r'<(?:input|select|textarea)[^>]*\bname="([^"]+)"', html))
    assert names == {"amount", "comment"}


# --------------------------------------------------------------------------
# Оформление возврата
# --------------------------------------------------------------------------


def test_refund_htmx_keeps_status_and_reduces_balance(client, student_id):
    """Возврат не меняет статус платежа, баланс уменьшается на сумму."""
    payment_id = _payment(student_id, amount=2400)

    response = client.post(
        f"/tutor/payments/{payment_id}/refund",
        data={"amount": "500", "comment": "Отмена урока"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.text == ""
    assert response.headers["HX-Trigger"] == "payment-saved"
    assert response.headers["HX-Reswap"] == "none"

    with SessionLocal() as session:
        assert session.get(AccountOperation, payment_id).status == "paid"
        assert balance(session, student_id) == 1900


def test_refund_without_htmx_redirects(client, student_id):
    """Без `HX-Request` — 303 на карточку ученика."""
    payment_id = _payment(student_id, amount=2400)

    response = client.post(
        f"/tutor/payments/{payment_id}/refund",
        data={"amount": "500"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tutor/students/{student_id}"


def test_refund_exceeding_remainder_shows_error(client, student_id):
    """Превышение остатка: диалог с доступной суммой и сообщением."""
    payment_id = _payment(student_id, amount=2400)

    response = client.post(
        f"/tutor/payments/{payment_id}/refund",
        data={"amount": "3000"},
        headers={"HX-Request": "true"},
    )

    html = response.text
    assert "больше доступной к возврату" in html
    assert "2\u00a0400\u00a0₽" in html
    assert "HX-Trigger" not in response.headers

    with SessionLocal() as session:
        assert balance(session, student_id) == 2400


def test_refund_of_pending_payment_shows_error(client, student_id):
    """Возврат по «Ожидает» отклоняется с сообщением о недопустимости."""
    payment_id = _payment(student_id, amount=2400, status="pending")

    response = client.post(
        f"/tutor/payments/{payment_id}/refund",
        data={"amount": "500"},
        headers={"HX-Request": "true"},
    )

    assert "только по платежу в статусе «Оплачено»" in response.text
    with SessionLocal() as session:
        assert balance(session, student_id) == 0


# --------------------------------------------------------------------------
# Изоляция
# --------------------------------------------------------------------------


def test_foreign_payment_refund_dialog_is_404(
    client, owner, tutor_factory, student_factory
):
    """Диалог возврата по чужому платежу — 404, а не 403."""
    foreign_student = student_factory(tutor_id=tutor_factory())
    payment_id = _payment(foreign_student)

    response = client.get(
        f"/tutor/payments/{payment_id}/refund/new", follow_redirects=False
    )

    assert response.status_code == 404


def test_foreign_payment_refund_create_is_404(
    client, owner, tutor_factory, student_factory
):
    """Возврат по чужому платежу — 404, операции не появляется."""
    foreign_student = student_factory(tutor_id=tutor_factory())
    payment_id = _payment(foreign_student)

    response = client.post(
        f"/tutor/payments/{payment_id}/refund",
        data={"amount": "500"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 404
    with SessionLocal() as session:
        assert (
            session.query(AccountOperation).filter_by(kind="refund").count() == 0
        )
