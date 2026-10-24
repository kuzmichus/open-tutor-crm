"""Тесты панели платежей и пересчёта через HTTP (задача 6.3).

Панель — фрагмент, который подменяет себя (`hx-swap="outerHTML"`), поэтому
проверяется разметка ответа: баланс, баннер и отсутствие баннера после
ремонта. Маршрут тот же, что у пользователя, — правило AGENTS.md.
"""

from datetime import UTC, datetime

import pytest

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="finance-panel@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "finance-panel@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def student_id(student_factory, owner):
    """Ученик вошедшего репетитора."""
    return student_factory(tutor_id=owner, first_name="Мария", last_name="Петрова")


def _completed_lesson(student_id: str, price: int = 1200) -> str:
    """Проведённый урок напрямую в БД — без списания."""
    with SessionLocal() as session:
        lesson = Lesson(
            student_id=student_id,
            type="individual",
            starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            duration_min=60,
            price=price,
            status="completed",
        )
        session.add(lesson)
        session.commit()
        return lesson.id


def test_panel_shows_balance(client, student_id):
    """Панель отдаёт карточку баланса и списки без ошибок шаблона."""
    response = client.get(f"/tutor/students/{student_id}/payments/panel")

    assert response.status_code == 200
    assert "Баланс ученика" in response.text
    assert "Платежей пока нет" in response.text


def test_panel_refreshes_itself_on_payment_saved(client, student_id):
    """Панель перезапрашивает себя по `payment-saved` (design D11).

    Без этого после сохранения платежа в диалоге баланс и история остались
    бы старыми до перезагрузки страницы.
    """
    html = client.get(f"/tutor/students/{student_id}/payments/panel").text

    assert 'id="student-finance-panel"' in html
    assert f'hx-get="/tutor/students/{student_id}/payments/panel"' in html
    assert 'hx-trigger="payment-saved from:body"' in html
    assert 'hx-swap="outerHTML"' in html


def test_panel_balance_equals_sum_of_operations(
    client, student_id, operation_factory
):
    """Баланс в разметке — та же сумма, что даёт история операций."""
    # Платёж 2000 и списание за урок 1200: остаток 800.
    operation_factory(student_id=student_id, amount=2000)
    _completed_lesson(student_id, price=1200)
    client.post(
        f"/tutor/students/{student_id}/balance/recalculate",
        headers=HTMX,
    )

    html = client.get(f"/tutor/students/{student_id}/payments/panel").text

    # «800 ₽» в карточке баланса и «+2 000 ₽» / «−1 200 ₽» в истории.
    assert "800\u00a0₽" in html
    assert "+2\u00a0000\u00a0₽" in html
    assert "\u22121\u00a0200\u00a0₽" in html


def test_panel_shows_banner_for_missing_charges(client, student_id):
    """Проведённый урок без списания включает баннер пересчёта."""
    _completed_lesson(student_id)

    response = client.get(f"/tutor/students/{student_id}/payments/panel")

    assert "Баланс не пересчитан" in response.text
    assert "Пересчитать" in response.text


def test_recalculate_returns_panel_without_banner(client, student_id):
    """POST пересчёта возвращает панель с новым балансом и без баннера."""
    _completed_lesson(student_id)

    response = client.post(
        f"/tutor/students/{student_id}/balance/recalculate", headers=HTMX
    )

    assert response.status_code == 200
    assert "Баланс не пересчитан" not in response.text
    assert "\u2212" in response.text  # списание уменьшило баланс
    assert "Урок" in response.text


def test_recalculate_without_htmx_redirects(client, student_id):
    """Без `HX-Request` пересчёт отвечает 303 на страницу ученика."""
    response = client.post(
        f"/tutor/students/{student_id}/balance/recalculate",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tutor/students/{student_id}"


def test_panel_foreign_student_is_404(client, owner, tutor_factory):
    """Панель чужого ученика отвечает как несуществующая."""
    foreign = tutor_factory(timezone="UTC")
    from app.student.models.student import Student

    with SessionLocal() as session:
        student = Student(tutor_id=foreign, first_name="Чужой", kind="child")
        session.add(student)
        session.commit()
        foreign_student_id = student.id

    response = client.get(f"/tutor/students/{foreign_student_id}/payments/panel")

    assert response.status_code == 404


# --------------------------------------------------------------------------
# Сводка на странице карточки: свой маршрут для перезапроса
# --------------------------------------------------------------------------


def test_card_summary_refreshes_itself_on_payment_saved(client, student_id):
    """Платёж вносится в модалке поверх страницы — сводка должна обновиться.

    Иначе после сохранения платежа на странице остался бы старый баланс,
    пока её не перезагрузят.
    """
    html = client.get(f"/tutor/students/{student_id}").text

    assert 'id="student-finance-summary"' in html
    assert f'hx-get="/tutor/students/{student_id}/finance/summary"' in html
    assert 'hx-trigger="payment-saved from:body"' in html
    assert 'hx-swap="outerHTML"' in html


def test_card_summary_fragment_shows_balance(client, student_id, operation_factory):
    """Фрагмент отдаёт ту же сводку, что и страница: баланс и операции."""
    operation_factory(student_id=student_id, amount=2000)

    response = client.get(f"/tutor/students/{student_id}/finance/summary")

    assert response.status_code == 200
    html = response.text
    assert 'id="student-finance-summary"' in html
    assert "Баланс ученика" in html
    assert "2\u00a0000\u00a0₽" in html
    # Фрагмент — самодостаточный корень, а не обёртка над страницей.
    assert html.lstrip().startswith("<section")


def test_card_summary_foreign_student_is_404(
    client, owner, tutor_factory, student_factory
):
    """Сводка чужого ученика отвечает как несуществующая."""
    foreign_student_id = student_factory(tutor_id=tutor_factory())

    response = client.get(
        f"/tutor/students/{foreign_student_id}/finance/summary",
        follow_redirects=False,
    )

    assert response.status_code == 404
