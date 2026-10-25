"""Тесты страницы финансов (`/tutor/finance`, change finance-page).

Поведение проверяется тем же путём, что у пользователя: те же маршруты,
поля формы и query-параметры; разметка ищется по тексту и атрибутам.
Даты строятся от «сейчас» (зона репетитора в тестах — UTC): прибитые
к октябрю тесты сломались бы в следующем месяце.

Ключевой сценарий сводки: ученик А принёс 2 000 (и 500 «ожидают»),
300 вернули, урок списал 1 200; ученик Б должен 1 200; ученик В имеет
переплату 800. Ожидающий платёж в доход не входит (design D4
student-finance).
"""

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.student.models.student import Student
from app.tutor.services.clock import utcnow

# Неразрывный пробел форматтера денег: «2 000 ₽» пишется без обычных пробелов.
NBSP = "\u00a0"

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


def _login(client, tutor_factory, email="fin@example.com", name="Финансист"):
    """Репетитор с зоной UTC (заводская умолчание) и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _money(value: int) -> str:
    """«2 000 ₽» — как форматирует finance.presentation.money."""
    return f"{value:,}".replace(",", NBSP) + NBSP + "₽"


def _operation(student_id: str, kind: str, amount: int, when: datetime, **extra):
    """Операция счёта напрямую в БД (для сводки важен только факт строки)."""
    with SessionLocal() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind=kind,
                amount=amount,
                occurred_at=when,
                **extra,
            )
        )
        session.commit()


def _first_day_of_month(months_ago: int) -> datetime:
    """Первое число месяца `months_ago` назад от сегодняшнего (UTC)."""
    today = utcnow()
    first = today.replace(day=1)
    for _ in range(months_ago):
        first = (first - timedelta(days=1)).replace(day=1)
    return first.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=UTC)


def _kpi_value(html: str, title: str) -> str:
    """Значение карточки сводки по её заголовку (блок: заголовок → число)."""
    match = re.search(
        rf'{re.escape(title)}</span>.*?fin-kpi__value[^"]*">\s*([^<]*?)\s*</p>',
        html,
        flags=re.S,
    )
    assert match, f"нет карточки «{title}»"
    return match.group(1)


def test_redirect_to_login_without_session(client):
    """Без сессии страница, партиал и диалог не отдают данные."""
    for url in ("/tutor/finance", "/tutor/finance/summary", "/tutor/payments/new"):
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/tutor/login")


def test_page_shows_summary_cards(client, tutor_factory, student_factory):
    """Карточки сводки: доход без ожидающих платежей, чистый доход, долги."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")
    debtor = student_factory(tutor_id=tutor_id, first_name="Борис")
    saver = student_factory(tutor_id=tutor_id, first_name="Вера")

    now = utcnow()
    _operation(payer, "payment", 2000, now, status="paid", method="transfer")
    _operation(payer, "payment", 500, now, status="pending", method="card")
    _operation(payer, "refund", 300, now)
    _operation(payer, "lesson", 1200, now)
    _operation(debtor, "lesson", 1200, now)
    _operation(saver, "payment", 800, now, status="paid", method="online")

    html = client.get("/tutor/finance").text
    # Доход — все оплаченные платежи репетитора: 2 000 Ани и 800 Веры.
    assert _kpi_value(html, "Доход") == _money(2800)
    assert _kpi_value(html, "Возвраты") == _money(300)
    assert _kpi_value(html, "Чистый доход") == _money(2500)
    assert _kpi_value(html, "Чистая прибыль") == _money(2500)
    assert _kpi_value(html, "Заработано (уроки)") == _money(2400)
    # Долг — типографский минус (U+2212), как у баланса карточки.
    assert _kpi_value(html, "Долги учеников") == f"\u2212{_money(1200)}"
    # Переплата — все положительные балансы: остаток Ани 500 и 800 Веры.
    assert _kpi_value(html, "Переплата") == _money(1300)
    assert "Расходы" in html  # карточка-заглушка на месте


def test_period_prev_excludes_current_month(client, tutor_factory, student_factory):
    """«Прошлый месяц» — окно одного месяца, платёж текущего не входит."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)

    prev_amount, current_amount = 7000, 900
    _operation(student_id, "payment", prev_amount, _first_day_of_month(1),
               status="paid", method="transfer")
    _operation(student_id, "payment", current_amount, utcnow(),
               status="paid", method="transfer")

    html = client.get("/tutor/finance?period=prev").text
    assert _kpi_value(html, "Доход") == _money(prev_amount)

    html_all = client.get("/tutor/finance?period=all").text
    assert _kpi_value(html_all, "Доход") == _money(prev_amount + current_amount)


def test_period_3m_and_unknown_fallback(client, tutor_factory, student_factory):
    """«Последние 3 месяца» берут текущий и два предыдущих; мусор — месяц."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)

    old, fresh = 5000, 600
    _operation(student_id, "payment", old, _first_day_of_month(2),
               status="paid", method="transfer")
    _operation(student_id, "payment", fresh, utcnow(),
               status="paid", method="transfer")

    html = client.get("/tutor/finance?period=3m").text
    assert _kpi_value(html, "Доход") == _money(old + fresh)

    # Мусор в query — не 500, а умолчание «Этот месяц» (design D2).
    fallback = client.get("/tutor/finance?period=nonsense").text
    assert _kpi_value(fallback, "Доход") == _money(fresh)


def test_compare_block_note(client, tutor_factory, student_factory):
    """Подсказка «заработано vs получено» следует за разницей (design D4)."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    now = utcnow()

    _operation(student_id, "payment", 5900, now, status="paid", method="transfer")
    _operation(student_id, "lesson", 4920, now)

    html = client.get("/tutor/finance").text
    assert "Заработано и получено" in html
    assert "платят вперёд" in html


def test_expense_button_opens_dialog(client, tutor_factory):
    """Кнопка «Расход» грузит диалог расхода в свой контейнер модалки."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance").text
    assert 'hx-get="/tutor/expenses/new"' in html
    assert 'hx-target="#modal-expense"' in html
    assert 'id="modal-expense"' in html


def test_income_dialog_offers_active_students(
    client, tutor_factory, student_factory
):
    """Диалог «Доход»: поле выбора ученика, архивные не предлагаются."""
    tutor_id = _login(client, tutor_factory)
    student_factory(tutor_id=tutor_id, first_name="Мария")
    student_factory(tutor_id=tutor_id, first_name="Архивный", status="archived")

    response = client.get("/tutor/payments/new", headers=HTMX)
    assert response.status_code == 200
    html = response.text
    assert 'hx-post="/tutor/payments"' in html
    assert "Ученик *" in html
    assert "Мария" in html
    assert "Архивный" not in html
    assert 'name="student_id"' in html


def test_income_create_success(client, tutor_factory, student_factory):
    """Платёж создаётся с учеником из формы и обновляет страницу событием."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id, first_name="Гриша")
    today = utcnow().strftime("%Y-%m-%d")

    response = client.post(
        "/tutor/payments",
        data={
            "student_id": student_id,
            "amount": "2000",
            "method": "transfer",
            "status": "paid",
            "date": today,
            "comment": "",
        },
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "payment-saved"

    with SessionLocal() as session:
        payments = list(
            session.scalars(
                select(AccountOperation).where(
                    AccountOperation.student_id == student_id,
                    AccountOperation.kind == "payment",
                )
            )
        )
    assert len(payments) == 1


def test_income_create_without_student_reopens_dialog(
    client, tutor_factory, student_factory
):
    """Ученик не выбран — ошибка валидации, а не 404 и не платёж."""
    tutor_id = _login(client, tutor_factory)
    today = utcnow().strftime("%Y-%m-%d")

    response = client.post(
        "/tutor/payments",
        data={
            "student_id": "",
            "amount": "1000",
            "method": "transfer",
            "status": "paid",
            "date": today,
        },
        headers=HTMX,
    )
    assert response.status_code == 200
    assert "Выберите ученика" in response.text

    with SessionLocal() as session:
        count = len(
            list(
                session.scalars(
                    select(AccountOperation).where(
                        AccountOperation.kind == "payment"
                    )
                )
            )
        )
    assert count == 0


def test_income_create_error_keeps_chosen_student(
    client, tutor_factory, student_factory
):
    """Ошибка в сумме не сбрасывает выбранного ученика (design D5)."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id, first_name="Даша")
    today = utcnow().strftime("%Y-%m-%d")

    response = client.post(
        "/tutor/payments",
        data={
            "student_id": student_id,
            "amount": "0",
            "method": "transfer",
            "status": "paid",
            "date": today,
        },
        headers=HTMX,
    )
    assert response.status_code == 200
    assert "больше нуля" in response.text
    assert f'data-initial-id="{student_id}"' in response.text
    assert "Даша" in response.text


def test_income_create_foreign_student_is_404(
    client, tutor_factory, student_factory
):
    """Чужой ученик в форме — как несуществующий (правило изоляции)."""
    _login(client, tutor_factory)
    foreign_id = student_factory()  # ученик свежесозданного репетитора
    today = utcnow().strftime("%Y-%m-%d")

    response = client.post(
        "/tutor/payments",
        data={
            "student_id": foreign_id,
            "amount": "1000",
            "method": "transfer",
            "status": "paid",
            "date": today,
        },
        headers=HTMX,
    )
    assert response.status_code == 404


def test_income_create_without_js_redirects(client, tutor_factory, student_factory):
    """Без HX-Request POST отвечает 303 на страницу финансов (design D6)."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    today = utcnow().strftime("%Y-%m-%d")

    response = client.post(
        "/tutor/payments",
        data={
            "student_id": student_id,
            "amount": "1500",
            "method": "card",
            "status": "paid",
            "date": today,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/finance"


def test_summary_partial_is_refreshable(client, tutor_factory, student_factory):
    """Партиал сводки существует и перезапрашивает себя по событиям."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    _operation(student_id, "payment", 1234, utcnow(),
               status="paid", method="transfer")

    response = client.get("/tutor/finance/summary?period=all")
    assert response.status_code == 200
    html = response.text
    assert 'id="finance-summary"' in html
    assert 'hx-trigger="payment-saved from:body, expense-saved from:body"' in html
    assert _money(1234) in html


def test_isolation_between_tutors(client, tutor_factory, student_factory):
    """Чужие ученики и суммы не видны ни на странице, ни в диалоге."""
    tutor_id = _login(client, tutor_factory)
    stranger = student_factory(first_name="Чужанин")
    _operation(stranger, "payment", 9999, utcnow(),
               status="paid", method="transfer")

    html = client.get("/tutor/finance").text
    assert _money(9999) not in html
    assert "Чужанин" not in html

    dialog = client.get("/tutor/payments/new", headers=HTMX).text
    assert "Чужанин" not in dialog


def test_income_button_on_page_opens_dialog(client, tutor_factory):
    """Кнопка «Доход» на странице грузит диалог в контейнер модалки."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance").text
    assert 'hx-get="/tutor/payments/new"' in html
    assert 'id="modal-payment"' in html
