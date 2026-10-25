"""Тесты расходов и секции операций страницы финансов (change finance-expenses).

Поведение проверяется тем же путём, что у пользователя: те же маршруты,
те же поля формы и query-параметры; разметка ищется по тексту и атрибутам.

Ключевой сценарий сводки: получено 2 000, расход 1 500 — «Осталось
репетитору» 500. Балансы: должник с −1 200 и переплатчик с +800.
"""

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.models.expense import Expense
from app.tutor.services.clock import utcnow

NBSP = "\u00a0"

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


def _login(client, tutor_factory, email="exp@example.com", name="Тратитель"):
    """Репетитор с зоной UTC (заводское умолчание) и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _money(value: int) -> str:
    """«1 500 ₽» — как форматирует finance.presentation.money."""
    return f"{abs(value):,}".replace(",", NBSP) + NBSP + "₽"


def _ops_section(html: str) -> str:
    """Разметка таблицы операций — без карточки балансов учеников.

    Имя ученика может легитимно встретиться в «Балансах учеников»
    (должник), поэтому проверки ленты смотрят только свою секцию.
    """
    match = re.search(
        r'<section class="card fin-ops".*?</section>', html, flags=re.S
    )
    assert match, "нет секции операций"
    return match.group(0)


def _expense(tutor_id: str, amount: int, when: datetime, **extra):
    """Расход напрямую в БД (для сводки важен только факт строки)."""
    with SessionLocal() as session:
        session.add(
            Expense(
                tutor_id=tutor_id,
                amount=amount,
                category=extra.pop("category", "rent"),
                spent_at=when,
                **extra,
            )
        )
        session.commit()


def _operation(student_id: str, kind: str, amount: int, when: datetime, **extra):
    """Операция счёта напрямую в БД."""
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


def test_redirect_to_login_without_session(client):
    """Без сессии диалог и создание расхода не отдают данные."""
    for method, url in (("get", "/tutor/expenses/new"), ("post", "/tutor/expenses")):
        response = getattr(client, method)(url, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/tutor/login")


def test_expense_dialog_fields(client, tutor_factory):
    """Диалог «Добавить расход»: сумма, дата, категории из закрытого списка."""
    _login(client, tutor_factory)
    response = client.get("/tutor/expenses/new")
    assert response.status_code == 200
    html = response.text
    assert "Добавить расход" in html
    assert 'hx-post="/tutor/expenses"' in html
    assert 'name="amount"' in html
    assert 'name="date"' in html
    assert 'name="category"' in html
    # Категории референса — по одной подписи из начала и конца списка.
    for category in ("Аренда", "Учебные материалы", "Программное обеспечение"):
        assert category in html


def test_expense_create_success(client, tutor_factory):
    """Расход создаётся от сессии репетитора и шлёт `expense-saved`."""
    tutor_id = _login(client, tutor_factory)
    today = utcnow().strftime("%Y-%m-%d")

    response = client.post(
        "/tutor/expenses",
        data={
            "amount": "1500",
            "category": "rent",
            "date": today,
            "comment": "кабинет",
        },
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "expense-saved"

    with SessionLocal() as session:
        expenses = list(session.scalars(select(Expense)))
    assert len(expenses) == 1
    assert expenses[0].tutor_id == tutor_id
    assert expenses[0].amount == 1500
    assert expenses[0].category == "rent"


def test_expense_create_errors_reopen_dialog(client, tutor_factory):
    """Нулевая сумма и чужая категория — ошибки формы, расхода нет."""
    _login(client, tutor_factory)
    today = utcnow().strftime("%Y-%m-%d")

    response = client.post(
        "/tutor/expenses",
        data={"amount": "0", "category": "rent", "date": today},
        headers=HTMX,
    )
    assert response.status_code == 200
    assert "больше нуля" in response.text
    assert "Добавить расход" in response.text

    response = client.post(
        "/tutor/expenses",
        data={"amount": "100", "category": "luxury", "date": today},
        headers=HTMX,
    )
    assert "категорию" in response.text

    with SessionLocal() as session:
        assert list(session.scalars(select(Expense))) == []


def test_expense_create_error_keeps_values(client, tutor_factory):
    """Ошибка в сумме не затирает категорию и комментарий."""
    _login(client, tutor_factory)
    today = utcnow().strftime("%Y-%m-%d")

    response = client.post(
        "/tutor/expenses",
        data={
            "amount": "abc",
            "category": "ads",
            "date": today,
            "comment": "пост ВК",
        },
        headers=HTMX,
    )
    assert "целое число" in response.text
    # Категория остаётся выбранной, комментарий — в поле.
    assert re.search(r'value="ads"[^>]*selected', response.text)
    assert "пост ВК" in response.text


def test_expense_create_without_js_redirects(client, tutor_factory):
    """Без HX-Request POST отвечает 303 на страницу финансов."""
    _login(client, tutor_factory)
    today = utcnow().strftime("%Y-%m-%d")

    response = client.post(
        "/tutor/expenses",
        data={"amount": "500", "category": "other", "date": today},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/finance"


def test_summary_counts_expenses_and_left_for_tutor(
    client, tutor_factory, student_factory
):
    """Сводка: расходы за период вычитаются, «Осталось репетитору» — итог."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id, first_name="Аня")

    _operation(student_id, "payment", 2000, utcnow(),
               status="paid", method="transfer")
    _expense(tutor_id, 1500, utcnow(), category="rent")

    html = client.get("/tutor/finance").text
    assert "− Расходы" in html
    assert "= Осталось репетитору" in html
    # 2 000 получено − 1 500 расход = 500 осталось.
    assert f"{_money(500)}" in html
    assert "Траты репетитора за период" in html
    # Положительный итог — зелёным.
    left = re.search(
        r"= Осталось репетитору.*?fin-compare__value([^\"]*)\">([^<]*)<",
        html,
        flags=re.S,
    )
    assert left, "нет строки «Осталось репетитору»"
    assert "fin-compare__value--green" in left.group(1)


def test_negative_left_for_tutor_is_red(client, tutor_factory):
    """Расходы больше полученного: итог отрицательный и подсвечен красным."""
    tutor_id = _login(client, tutor_factory)
    _expense(tutor_id, 3000, utcnow(), category="rent")

    html = client.get("/tutor/finance").text
    left = re.search(
        r"= Осталось репетитору.*?fin-compare__value([^\"]*)\">([^<]*)<",
        html,
        flags=re.S,
    )
    assert left, "нет строки «Осталось репетитору»"
    assert "fin-compare__value--red" in left.group(1)
    # Минус — типографский (U+2212), как у долгов.
    assert left.group(2).startswith("\u2212")


def test_expense_outside_period_excluded(client, tutor_factory):
    """Расход прошлого месяца не попадает в сводку текущего."""
    tutor_id = _login(client, tutor_factory)
    prev_month = (utcnow().replace(day=1) - timedelta(days=1)).replace(
        day=1, hour=12, tzinfo=UTC
    )
    _expense(tutor_id, 7000, prev_month)

    html = client.get("/tutor/finance").text
    assert _money(7000) not in html

    html_all = client.get("/tutor/finance?period=all").text
    assert _money(7000) in html_all


def test_summary_and_operations_refresh_on_expense_saved(client, tutor_factory):
    """Партиалы перезапрашивают себя по событию `expense-saved`."""
    _login(client, tutor_factory)

    summary = client.get("/tutor/finance/summary?period=month").text
    assert 'hx-trigger="payment-saved from:body, expense-saved from:body"' in summary

    operations = client.get("/tutor/finance/operations?period=month&tab=all").text
    assert 'id="finance-operations"' in operations
    assert 'hx-trigger="payment-saved from:body, expense-saved from:body"' in operations


def test_tabs_present_on_page(client, tutor_factory):
    """Пять вкладок по референсу; заглушки помечены как разработка."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance").text
    for label in (
        "Все операции",
        "Расходы",
        "Доходы",
        "Аналитика",
        "Прогноз на месяц",
    ):
        assert label in html

    analytics = client.get("/tutor/finance?tab=analytics").text
    assert "Раздел в разработке" in analytics
    forecast = client.get("/tutor/finance?tab=forecast").text
    assert "Раздел в разработке" in forecast

    # Мусор в query — умолчание «Все операции» (активная вкладка).
    fallback = client.get("/tutor/finance?tab=nonsense").text
    assert re.search(
        r'class="tab tab--active"[^>]*href="/tutor/finance\?period=month&tab=all"',
        fallback,
    )


def test_feed_all_income_expenses_tabs(client, tutor_factory, student_factory):
    """Вкладки фильтруют ленту: платежи+возвраты+расходы / только доходы."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")
    other = student_factory(tutor_id=tutor_id, first_name="Борис")

    now = utcnow()
    _operation(payer, "payment", 2000, now, status="paid", method="transfer")
    _operation(payer, "refund", 300, now)
    _operation(other, "lesson", 1200, now)
    _expense(tutor_id, 1500, now, category="ads", comment="пост ВК")

    all_html = client.get("/tutor/finance?period=all&tab=all").text
    all_ops = _ops_section(all_html)
    assert "Аня" in all_ops
    assert "Реклама" in all_ops  # категория расхода — заголовок строки
    assert "пост ВК" in all_ops
    # Списание за урок — движение баланса ученика, не деньги репетитора:
    # в ленту не попадает (но в «Балансах учеников» Борис-должник есть).
    assert "Борис" not in all_ops
    assert "Борис" in all_html  # карточка балансов показывает долг

    income_ops = _ops_section(
        client.get("/tutor/finance?period=all&tab=income").text
    )
    assert "Аня" in income_ops
    assert "Реклама" not in income_ops

    expenses_ops = _ops_section(
        client.get("/tutor/finance?period=all&tab=expenses").text
    )
    assert "Реклама" in expenses_ops
    assert "Аня" not in expenses_ops


def test_feed_empty_state(client, tutor_factory):
    """Пустой период — сообщение, а не пустая таблица."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance").text
    assert "операций нет" in html


def test_balances_card_lists_debtors_and_overpayers(
    client, tutor_factory, student_factory
):
    """Карточка «Балансы учеников»: должники красным, переплата зелёным."""
    tutor_id = _login(client, tutor_factory)
    debtor = student_factory(tutor_id=tutor_id, first_name="Борис")
    saver = student_factory(tutor_id=tutor_id, first_name="Вера")

    now = utcnow()
    _operation(debtor, "lesson", 1200, now)
    _operation(saver, "payment", 800, now, status="paid", method="online")

    html = client.get("/tutor/finance").text
    assert "Балансы учеников" in html
    assert "Должники (1)" in html
    assert "Переплата (1)" in html
    assert "Борис" in html
    assert "Вера" in html
    # Долг — с типографским минусом (U+2212).
    assert f"\u2212{_money(1200)}" in html
    assert _money(800) in html


def test_balances_card_empty_note(client, tutor_factory):
    """Без долгов и переплат карточка говорит об этом, а не пустеет."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance").text
    assert "нулевой баланс" in html
    assert "долгов и переплат нет" in html


def test_isolation_between_tutors(client, tutor_factory):
    """Чужие расходы не видны ни в сводке, ни в ленте."""
    tutor_id = _login(client, tutor_factory)
    stranger_id = tutor_factory(name="Чужой")
    _expense(stranger_id, 9999, utcnow(), category="rent")

    html = client.get("/tutor/finance?period=all").text
    assert _money(9999) not in html

    expenses_html = client.get("/tutor/finance?period=all&tab=expenses").text
    assert _money(9999) not in expenses_html

    # Свой расход виден.
    _expense(tutor_id, 100, utcnow(), category="other")
    expenses_html = client.get("/tutor/finance?period=all&tab=expenses").text
    assert _money(100) in expenses_html
