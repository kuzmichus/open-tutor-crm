"""Сквозной сценарий счёта ученика из user story (задача 10.2).

Один ученик, один репетитор, весь путь через HTTP — те же маршруты и поля
формы, что у пользователя (правило AGENTS.md):

```
ученик без операций          баланс 0
внесение платежа 2000        баланс 2000
проведение урока 1200        баланс 800
возврат 500                  баланс 300
```

Проверяется не только итоговое число, но и то, что его подтверждают три
независимых представления: карточка баланса в панели, строки истории в
обратном хронологическом порядке и сумма со знаком у каждой строки.
Расхождение между ними — это и есть ошибка, которую увидит пользователь.
"""

from datetime import datetime

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import balance
from app.lesson.models.lesson import Lesson

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="finance-story@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "finance-story@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def student_id(student_factory, owner):
    """Ученик вошедшего репетитора без единой операции."""
    return student_factory(tutor_id=owner, first_name="Мария", last_name="Петрова")


def _pay(client, student_id: str, amount: int) -> None:
    """Вносит оплату через диалог платежа."""
    response = client.post(
        f"/tutor/students/{student_id}/payments",
        data={
            "amount": str(amount),
            "method": "transfer",
            "status": "paid",
            "date": "2026-10-22",
            "comment": "",
        },
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "payment-saved"


def _planned_lesson(student_id: str, price: int) -> str:
    """Запланированный урок напрямую в БД: списания у него ещё нет."""
    with SessionLocal() as session:
        lesson = Lesson(
            student_id=student_id,
            type="individual",
            starts_at=datetime(2026, 10, 19, 10, 0),
            duration_min=60,
            price=price,
            status="planned",
        )
        session.add(lesson)
        session.commit()
        return lesson.id


def _complete_lesson(client, student_id: str, lesson_id: str, price: int) -> None:
    """Проводит урок через форму правки — единственный путь к списанию."""
    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data={
            "type": "individual",
            "student_id": student_id,
            "starts_at": "2026-10-19T10:00",
            "duration_min": "60",
            "price": str(price),
            "status": "completed",
            "note": "",
            "meeting_url": "",
        },
        headers=HTMX,
    )
    assert response.status_code == 200


def _refund(client, payment_id: str, amount: int) -> None:
    """Оформляет возврат по платежу."""
    response = client.post(
        f"/tutor/payments/{payment_id}/refund",
        data={"amount": str(amount), "comment": "Отмена занятия"},
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "payment-saved"


def _payment_id(student_id: str) -> str:
    """Единственный платёж ученика — для возврата по нему."""
    with SessionLocal() as session:
        return session.scalars(
            select(AccountOperation.id).where(
                AccountOperation.student_id == student_id,
                AccountOperation.kind == "payment",
            )
        ).one()


def test_user_story_balance_walks_from_zero_to_three_hundred(client, student_id):
    """Платёж 2000 → урок 1200 → возврат 500 дают баланс 300 и три строки."""
    # 1. Ученик без операций: баланс ноль, история пуста.
    panel = client.get(f"/tutor/students/{student_id}/payments/panel").text
    assert "0\u00a0₽" in panel
    assert "Операций пока нет" in panel
    with SessionLocal() as session:
        assert balance(session, student_id) == 0

    # 2. Внесение платежа 2000.
    _pay(client, student_id, 2000)
    with SessionLocal() as session:
        assert balance(session, student_id) == 2000
    panel = client.get(f"/tutor/students/{student_id}/payments/panel").text
    assert "2\u00a0000\u00a0₽" in panel
    assert "+2\u00a0000\u00a0₽" in panel

    # 3. Проведение урока 1200: списание создаёт путь правки урока.
    lesson_id = _planned_lesson(student_id, 1200)
    _complete_lesson(client, student_id, lesson_id, 1200)
    with SessionLocal() as session:
        assert balance(session, student_id) == 800
    panel = client.get(f"/tutor/students/{student_id}/payments/panel").text
    assert "800\u00a0₽" in panel
    assert "\u22121\u00a0200\u00a0₽" in panel

    # 4. Возврат 500 по платежу.
    payment_id = _payment_id(student_id)
    _refund(client, payment_id, 500)
    with SessionLocal() as session:
        assert balance(session, student_id) == 300

    # 5. Панель показывает 300 и все три строки в обратном порядке.
    panel = client.get(f"/tutor/students/{student_id}/payments/panel").text
    assert "300\u00a0₽" in panel
    for amount in ("+2\u00a0000\u00a0₽", "\u22121\u00a0200\u00a0₽", "\u2212500\u00a0₽"):
        assert amount in panel, amount

    # История — от новых к старым. Возврат получает момент сохранения и
    # стоит первым; дальше идут платёж (22 октября) и урок (19 октября).
    history = panel[panel.index("История операций") :]
    assert (
        history.index("\u2212500\u00a0₽")
        < history.index("+2\u00a0000\u00a0₽")
        < history.index("\u22121\u00a0200\u00a0₽")
    )


def test_user_story_balance_matches_operation_sum(client, student_id):
    """Баланс равен сумме операций со знаком — на каждом шаге сценария."""
    _pay(client, student_id, 2000)
    lesson_id = _planned_lesson(student_id, 1200)
    _complete_lesson(client, student_id, lesson_id, 1200)
    _refund(client, _payment_id(student_id), 500)

    with SessionLocal() as session:
        rows = session.query(AccountOperation).filter_by(student_id=student_id).all()
        expected = sum(
            row.amount if row.kind == "payment" else -row.amount for row in rows
        )
        assert expected == 300
        assert balance(session, student_id) == expected
        assert len(rows) == 3


def test_user_story_card_page_shows_final_balance(client, student_id):
    """Страница карточки ученика показывает тот же итог, что и панель."""
    _pay(client, student_id, 2000)
    lesson_id = _planned_lesson(student_id, 1200)
    _complete_lesson(client, student_id, lesson_id, 1200)
    _refund(client, _payment_id(student_id), 500)

    html = client.get(f"/tutor/students/{student_id}").text
    start = html.index("Счёт ученика")
    block = html[start : html.index("</section>", start)]

    assert "300\u00a0₽" in block
    # Сводка показывает последние операции — все три помещаются.
    for amount in ("+2\u00a0000\u00a0₽", "\u22121\u00a0200\u00a0₽", "\u2212500\u00a0₽"):
        assert amount in block, amount
