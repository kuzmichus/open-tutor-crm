"""Тесты диалога платежа: маршруты, ответы и разметка формы.

Проверяется поведение через HTTP — теми же маршрутами и полями формы, что
у пользователя (правило AGENTS.md): открытие диалога, ответ на ошибку
(фрагмент диалога) и на успех (закрытие + `payment-saved`), 303 без
`HX-Request` и изоляция по репетитору.
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
        email="finance-views-owner@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "finance-views-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def student_id(student_factory, owner):
    """Ученик вошедшего репетитора."""
    return student_factory(tutor_id=owner, first_name="Мария", last_name="Петрова")


def _form(**overrides) -> dict:
    values = {
        "amount": "2000",
        "method": "transfer",
        "status": "paid",
        "date": "2026-10-22",
        "comment": "",
    }
    values.update(overrides)
    return values


def _payment(student_id: str, amount: int = 2000, **extra) -> str:
    """Платёж напрямую в БД; возвращает его id."""
    from datetime import UTC, datetime

    with SessionLocal() as session:
        payment = AccountOperation(
            student_id=student_id,
            kind="payment",
            amount=amount,
            occurred_at=datetime(2026, 10, 22, 1, 31, tzinfo=UTC),
            status=extra.pop("status", "paid"),
            method=extra.pop("method", "card"),
            **extra,
        )
        session.add(payment)
        session.commit()
        return payment.id


# --------------------------------------------------------------------------
# Открытие диалога
# --------------------------------------------------------------------------


def test_new_payment_dialog_has_empty_form(client, student_id):
    """GET формы: пустая сумма, умолчания «Оплачено»/«Перевод»."""
    response = client.get(f"/tutor/students/{student_id}/payments/new")

    assert response.status_code == 200
    html = response.text
    assert 'id="modal-payment"' in html
    assert "Новый платёж" in html
    # Сумма пуста, статус и способ — по умолчанию.
    assert re.search(r'id="payment-amount"[^>]*value=""', html)
    assert '<option value="paid"\n                                    selected>' in html
    assert '<option value="transfer"\n                                    selected>' in html


def test_edit_payment_dialog_shows_saved_values(client, student_id):
    """GET правки: поля заполнены значениями платежа."""
    payment_id = _payment(student_id, amount=2400, method="card", status="pending")

    response = client.get(f"/tutor/payments/{payment_id}/edit")

    assert response.status_code == 200
    html = response.text
    assert "Платёж" in html
    assert 'value="2400"' in html
    # Дата — день платежа в зоне педагога (UTC): 22.10.2026.
    assert 'value="2026-10-22"' in html
    assert "Ожидает" in html


def test_payment_dialog_has_no_student_select(client, student_id):
    """Ученик в диалоге — статичный текст, а не селект (design D11).

    Селекта ученика нет вовсе: перенос платежа другому ученику — отдельный
    сценарий, которого в требованиях нет. Поле «Ученик» не имеет `name`,
    поэтому в POST уходят только поля платежа.
    """
    response = client.get(f"/tutor/students/{student_id}/payments/new")

    html = response.text
    assert "Мария Петрова" in html
    # Ни одного <select name="student_id"> и ни одного поля с этим именем.
    assert 'name="student_id"' not in html
    assert "<select" in html  # селекты способа и статуса есть
    assert 'name="method"' in html
    assert 'name="status"' in html
    # Форма отправляет только свои поля — их ровно пять.
    names = set(re.findall(r'<(?:input|select|textarea)[^>]*\bname="([^"]+)"', html))
    assert names == {"amount", "method", "status", "date", "comment"}


def test_payment_dialog_targets_its_own_container(client, student_id):
    """Форма метит в `#modal-payment`, а не в `#modal` (design D10)."""
    response = client.get(f"/tutor/students/{student_id}/payments/new")

    html = response.text
    assert 'hx-target="#modal-payment"' in html
    assert 'hx-swap="outerHTML"' in html
    assert 'hx-post="/tutor/students/%s/payments"' % student_id in html


# --------------------------------------------------------------------------
# Создание: оба пути ответа
# --------------------------------------------------------------------------


def test_create_payment_htmx_closes_dialog_and_triggers_event(client, student_id):
    """Успех: пустое тело, `payment-saved` и отсутствие подмены DOM."""
    response = client.post(
        f"/tutor/students/{student_id}/payments",
        data=_form(),
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.text == ""
    assert response.headers["HX-Trigger"] == "payment-saved"
    # Пустое тело с outerHTML дало бы htmx:swapError — подмены быть не должно.
    assert response.headers["HX-Reswap"] == "none"

    with SessionLocal() as session:
        assert balance(session, student_id) == 2000


def test_create_payment_without_htmx_redirects(client, student_id):
    """Без `HX-Request` — 303 на карточку ученика: форма работает без JS."""
    response = client.post(
        f"/tutor/students/{student_id}/payments",
        data=_form(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tutor/students/{student_id}"

    with SessionLocal() as session:
        assert balance(session, student_id) == 2000


def test_create_payment_with_invalid_amount_returns_dialog(client, student_id):
    """Ошибка: тот же диалог с сообщением и присланными значениями."""
    response = client.post(
        f"/tutor/students/{student_id}/payments",
        data=_form(amount="0"),
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    html = response.text
    assert 'id="modal-payment"' in html
    assert "Сумма платежа должна быть больше нуля." in html
    # Диалог не закрыт: событие успеха не отправлено.
    assert "HX-Trigger" not in response.headers

    with SessionLocal() as session:
        assert session.query(AccountOperation).all() == []
        assert balance(session, student_id) == 0


def test_create_payment_keeps_entered_values_on_error(client, student_id):
    """Повторная отрисовка показывает введённое, а не сброшенную форму."""
    response = client.post(
        f"/tutor/students/{student_id}/payments",
        data=_form(amount="0", comment="За ноябрь", date="2026-11-03"),
        headers={"HX-Request": "true"},
    )

    html = response.text
    assert "За ноябрь" in html
    assert 'value="2026-11-03"' in html


# --------------------------------------------------------------------------
# Правка: оба пути ответа
# --------------------------------------------------------------------------


def test_update_payment_htmx_changes_balance(client, student_id):
    """Правка суммы 2400 → 2000: диалог закрыт, баланс пересчитан."""
    payment_id = _payment(student_id, amount=2400)

    response = client.post(
        f"/tutor/payments/{payment_id}",
        data=_form(amount="2000"),
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.text == ""
    assert response.headers["HX-Trigger"] == "payment-saved"

    with SessionLocal() as session:
        assert session.get(AccountOperation, payment_id).amount == 2000
        assert balance(session, student_id) == 2000


def test_update_payment_without_htmx_redirects_to_card(client, student_id):
    """Без `HX-Request` — 303 на карточку ученика."""
    payment_id = _payment(student_id)

    response = client.post(
        f"/tutor/payments/{payment_id}",
        data=_form(amount="1500"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tutor/students/{student_id}"


def test_cancel_payment_with_refund_shows_error_in_dialog(client, student_id):
    """Отмена платежа с возвратом: сообщение в диалоге, статус не меняется."""
    from datetime import UTC, datetime

    payment_id = _payment(student_id, amount=2000)
    with SessionLocal() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="refund",
                amount=500,
                occurred_at=datetime(2026, 10, 22, 2, 0, tzinfo=UTC),
                payment_id=payment_id,
            )
        )
        session.commit()

    response = client.post(
        f"/tutor/payments/{payment_id}",
        data=_form(amount="2000", status="cancelled"),
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Нельзя отменить платёж" in response.text
    assert "HX-Trigger" not in response.headers

    with SessionLocal() as session:
        assert session.get(AccountOperation, payment_id).status == "paid"


# --------------------------------------------------------------------------
# Изоляция
# --------------------------------------------------------------------------


def test_foreign_payment_edit_is_404(client, owner, tutor_factory, student_factory):
    """Чужой платёж в форме правки — 404, а не 403."""
    foreign_student = student_factory(tutor_id=tutor_factory())
    payment_id = _payment(foreign_student)

    response = client.get(
        f"/tutor/payments/{payment_id}/edit", follow_redirects=False
    )

    assert response.status_code == 404


def test_foreign_payment_update_is_404(client, owner, tutor_factory, student_factory):
    """Чужой платёж в сохранении — 404, запись не меняется."""
    foreign_student = student_factory(tutor_id=tutor_factory())
    payment_id = _payment(foreign_student, amount=2400)

    response = client.post(
        f"/tutor/payments/{payment_id}",
        data=_form(amount="100"),
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 404
    with SessionLocal() as session:
        assert session.get(AccountOperation, payment_id).amount == 2400


def test_foreign_student_new_payment_is_404(
    client, owner, tutor_factory, student_factory
):
    """Диалог платежа чужого ученика — 404."""
    foreign_student = student_factory(tutor_id=tutor_factory())

    assert (
        client.get(
            f"/tutor/students/{foreign_student}/payments/new", follow_redirects=False
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/tutor/students/{foreign_student}/payments",
            data=_form(),
            headers={"HX-Request": "true"},
            follow_redirects=False,
        ).status_code
        == 404
    )


def test_lesson_charge_cannot_be_opened_as_payment(client, student_id, lesson_factory):
    """Списание не открывается в форме платежа: это не платёж, а урок."""
    from datetime import UTC, datetime

    lesson_id = lesson_factory(student_id=student_id)
    with SessionLocal() as session:
        operation = AccountOperation(
            student_id=student_id,
            kind="lesson",
            amount=1200,
            occurred_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            lesson_id=lesson_id,
        )
        session.add(operation)
        session.commit()
        operation_id = operation.id

    assert client.get(f"/tutor/payments/{operation_id}/edit").status_code == 404


def test_payment_dialog_requires_login(client, student_id):
    """Без сессии диалог перенаправляет на вход, а не показывает данные."""
    client.cookies.clear()

    response = client.get(
        f"/tutor/students/{student_id}/payments/new", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
