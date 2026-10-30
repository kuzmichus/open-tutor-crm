"""Изоляция счёта ученика между репетиторами (задача 10.1).

Правило AGENTS.md: чужая запись и несуществующая неразличимы — 404, а не
403, потому что существование чужой записи не раскрывается. У операции
счёта нет своего `tutor_id` (design D2), владелец выводится из ученика,
поэтому проверяется каждый маршрут: диалоги, сохранение, возврат,
пересчёт и счёт за период.

Отдельно проверяется, что панель показывает только операции своего
репетитора: она собирается сервисом по `student_id`, а не по сессии,
и ошибка в выборке была бы тихой утечкой данных.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import balance
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from main import app

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


def _login(email: str) -> TestClient:
    """Клиент с собственной сессией указанного репетитора."""
    client = TestClient(app)
    response = client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client


@pytest.fixture()
def two_tutors(tutor_factory):
    """Два репетитора, у каждого ученик с платежом и проведённым уроком.

    Возвращает id и готовые клиенты (уже вошедшие). У каждого ученика свои
    операции, чтобы утечка была видна по суммам и по именам.
    """
    tutor_a = tutor_factory(email="finance-iso-a@example.com", password=PASSWORD)
    tutor_b = tutor_factory(email="finance-iso-b@example.com", password=PASSWORD)

    with SessionLocal() as db:
        student_a = Student(tutor_id=tutor_a, first_name="Алиса", last_name="Своя")
        student_b = Student(tutor_id=tutor_b, first_name="Борис", last_name="Чужой")
        db.add_all([student_a, student_b])
        db.flush()

        payment_a = AccountOperation(
            student_id=student_a.id,
            kind="payment",
            amount=2000,
            occurred_at=datetime(2026, 10, 22, 1, 31, tzinfo=UTC),
            status="paid",
            method="transfer",
        )
        payment_b = AccountOperation(
            student_id=student_b.id,
            kind="payment",
            amount=7700,
            occurred_at=datetime(2026, 10, 22, 2, 0, tzinfo=UTC),
            status="paid",
            method="card",
        )
        db.add_all([payment_a, payment_b])
        db.flush()

        lesson_b = Lesson(
            student_id=student_b.id,
            type="individual",
            starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            duration_min=60,
            price=1200,
            status="completed",
        )
        db.add(lesson_b)
        db.commit()

        ids = {
            "tutor_a": tutor_a,
            "tutor_b": tutor_b,
            "student_a": student_a.id,
            "student_b": student_b.id,
            "payment_a": payment_a.id,
            "payment_b": payment_b.id,
        }

    client_a = _login("finance-iso-a@example.com")
    client_b = _login("finance-iso-b@example.com")
    yield {**ids, "client_a": client_a, "client_b": client_b}
    client_a.close()
    client_b.close()


# --------------------------------------------------------------------------
# Чужие операции: 404 вместо 403
# --------------------------------------------------------------------------

# Пары «маршрут чужой страницы → текст, который не должен утечь»: у каждой
# страницы свой признак — имя чужого ученика или его сумма.
_FOREIGN_GET_PAGES = [
    pytest.param("/tutor/payments/{payment}/edit", "7\u00a0700", id="payment-edit"),
    pytest.param("/tutor/payments/{payment}/refund/new", "7\u00a0700", id="refund-dialog"),
    pytest.param("/tutor/students/{student}/payments/new", "Борис", id="payment-new"),
    pytest.param("/tutor/students/{student}/payments/panel", "7\u00a0700", id="panel"),
    pytest.param("/tutor/students/{student}/invoice", "Борис", id="invoice"),
    pytest.param("/tutor/students/{student}/edit?tab=payments", "7\u00a0700", id="student-edit"),
]

@pytest.mark.parametrize(("path", "foreign_text"), _FOREIGN_GET_PAGES)
def test_foreign_finance_page_is_404(path, foreign_text, two_tutors):
    """Страница чужого ученика отвечает как несуществующая и не отдаёт данные."""
    url = path.format(
        payment=two_tutors["payment_b"], student=two_tutors["student_b"]
    )

    response = two_tutors["client_a"].get(url, follow_redirects=False)

    assert response.status_code == 404
    assert foreign_text not in response.text



def test_foreign_payment_update_is_404(two_tutors):
    """Сохранение чужого платежа не меняет ни сумму, ни баланс."""
    response = two_tutors["client_a"].post(
        f"/tutor/payments/{two_tutors['payment_b']}",
        data={
            "amount": "1",
            "method": "card",
            "status": "paid",
            "date": "2026-10-22",
            "comment": "",
        },
        headers=HTMX,
        follow_redirects=False,
    )

    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.get(AccountOperation, two_tutors["payment_b"]).amount == 7700
        assert balance(db, two_tutors["student_b"]) == 7700


def test_foreign_refund_create_is_404(two_tutors):
    """Возврат по чужому платежу не создаёт операции."""
    response = two_tutors["client_a"].post(
        f"/tutor/payments/{two_tutors['payment_b']}/refund",
        data={"amount": "500"},
        headers=HTMX,
        follow_redirects=False,
    )

    assert response.status_code == 404
    with SessionLocal() as db:
        assert (
            db.query(AccountOperation)
            .filter(AccountOperation.kind == "refund")
            .count()
            == 0
        )
        assert balance(db, two_tutors["student_b"]) == 7700


def test_foreign_payment_create_is_404(two_tutors):
    """Платёж чужому ученику не создаётся."""
    response = two_tutors["client_a"].post(
        f"/tutor/students/{two_tutors['student_b']}/payments",
        data={
            "amount": "100",
            "method": "card",
            "status": "paid",
            "date": "2026-10-22",
            "comment": "",
        },
        headers=HTMX,
        follow_redirects=False,
    )

    assert response.status_code == 404
    with SessionLocal() as db:
        assert balance(db, two_tutors["student_b"]) == 7700


def test_foreign_recalculate_is_404(two_tutors):
    """Пересчёт чужого ученика не добавляет списаний."""
    response = two_tutors["client_a"].post(
        f"/tutor/students/{two_tutors['student_b']}/balance/recalculate",
        headers=HTMX,
        follow_redirects=False,
    )

    assert response.status_code == 404
    with SessionLocal() as db:
        assert (
            db.query(AccountOperation)
            .filter(AccountOperation.kind == "lesson")
            .count()
            == 0
        )


# --------------------------------------------------------------------------
# Панель показывает только свои операции
# --------------------------------------------------------------------------


def test_panel_shows_only_own_operations(two_tutors):
    """В панели ученика A нет ни сумм, ни имени ученика B."""
    html = two_tutors["client_a"].get(
        f"/tutor/students/{two_tutors['student_a']}/payments/panel"
    ).text

    assert "2\u00a0000\u00a0₽" in html
    assert "7\u00a0700\u00a0₽" not in html
    assert "Борис" not in html
    # История ограничена операциями своего ученика.
    assert "Урок" not in html


def test_card_page_shows_only_own_balance(two_tutors):
    """Сводка на странице ученика A считает только его операции."""
    html = two_tutors["client_a"].get(
        f"/tutor/students/{two_tutors['student_a']}"
    ).text

    assert "2\u00a0000\u00a0₽" in html
    assert "7\u00a0700\u00a0₽" not in html


def test_login_required_for_finance_routes(client):
    """Без сессии счёт не отдаётся: редирект на вход (спека student-finance)."""
    response = client.get("/tutor/payments/anything/edit", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/tutor/login")
