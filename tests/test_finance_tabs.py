"""Тесты htmx-навигации вкладок страницы финансов (change finance-tabs-htmx).

Клик по вкладке не перезагружает страницу: ссылка несёт `hx-get` на ручку
содержимого вкладки `/tutor/finance/tabs/{tab}`, а ответ — та же секция
операций, что рендерит страница. Проверяем тем же путём, что у пользователя:
маршруты, query-параметры и атрибуты разметки.

Без JS страница работает как раньше: `href` вкладки — обычный адрес страницы
с периодом и вкладкой.
"""

import html as html_lib
import re

from app.tutor.services.clock import utcnow

PASSWORD = "Секретный-Пароль-1"


def _plain(markup: str) -> str:
    """Разметка с раскрытыми HTML-сущностями.

    Адреса вкладок собирает сервис и подставляет их в атрибуты через Jinja,
    поэтому `&` в ответе записан как `&amp;` — это правильный HTML, браузер
    и htmx читают его как `&`. Тесты сравнивают адреса в привычном виде.
    """
    return html_lib.unescape(markup)


def _login(client, tutor_factory, email="tabs@example.com", name="Вкладочник"):
    """Репетитор с зоной UTC и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def test_tab_links_load_partial_via_htmx(client, tutor_factory):
    """Вкладка несёт hx-get на ручку содержимого и hx-target на секцию."""
    _login(client, tutor_factory)
    html = _plain(client.get("/tutor/finance").text)

    for key in ("all", "expenses", "income", "analytics", "forecast"):
        # href остаётся адресом страницы — вкладка работает без JS.
        assert f'href="/tutor/finance?period=month&tab={key}"' in html
        # hx-get — ручка, отдающая только содержимое вкладки.
        assert f'hx-get="/tutor/finance/tabs/{key}?period=month"' in html

    assert 'hx-target="#finance-operations"' in html
    assert 'hx-swap="outerHTML"' in html


def test_tab_endpoint_returns_section_only(client, tutor_factory):
    """Ручка вкладки отдаёт секцию операций, а не страницу целиком."""
    _login(client, tutor_factory)
    response = client.get("/tutor/finance/tabs/expenses?period=month")

    assert response.status_code == 200
    body = _plain(response.text)
    assert 'id="finance-operations"' in body
    # Страница целиком сюда не попадает: ни сайдбара, ни сводки, ни шапки.
    assert "<html" not in body
    assert "finance-summary" not in body
    assert "sidebar" not in body
    # Активная вкладка — та, что в пути.
    assert re.search(
        r'class="tab tab--active"[^>]*href="/tutor/finance\?period=month&tab=expenses"',
        body,
    )


def test_tab_endpoint_pushes_page_url_into_history(client, tutor_factory):
    """Адрес в истории — страница с этой вкладкой, а не адрес партиала."""
    _login(client, tutor_factory)
    response = client.get("/tutor/finance/tabs/income?period=prev")

    assert response.headers["HX-Push-Url"] == "/tutor/finance?period=prev&tab=income"


def test_tab_endpoint_keeps_analytics_horizon(client, tutor_factory):
    """Горизонт «Аналитики» переживает переключение и попадает в адрес."""
    _login(client, tutor_factory)
    response = client.get("/tutor/finance/tabs/analytics?period=month&months=12")

    assert "Доходы и расходы по месяцам" in response.text
    assert (
        response.headers["HX-Push-Url"]
        == "/tutor/finance?period=month&tab=analytics&months=12"
    )


def test_tab_endpoint_unknown_tab_falls_back_to_all(client, tutor_factory):
    """Опечатка в пути — умолчание «Все операции», а не 404."""
    _login(client, tutor_factory)
    response = client.get("/tutor/finance/tabs/nonsense?period=month")

    assert response.status_code == 200
    assert re.search(
        r'class="tab tab--active"[^>]*href="/tutor/finance\?period=month&tab=all"',
        _plain(response.text),
    )
    assert response.headers["HX-Push-Url"] == "/tutor/finance?period=month&tab=all"


def test_tab_endpoint_requires_login(client):
    """Без сессии ручка вкладки отправляет на вход, а не отдаёт данные."""
    response = client.get("/tutor/finance/tabs/all", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_tab_response_carries_period_state_oob(client, tutor_factory):
    """Ответ вкладки подменяет и скрытые поля формы периода.

    Форма периода живёт вне секции операций, поэтому без этой подмены
    следующая смена периода отправила бы прежнюю вкладку.
    """
    _login(client, tutor_factory)
    partial = client.get("/tutor/finance/tabs/analytics?period=month&months=12").text
    assert 'id="finance-period-state" hx-swap-oob="outerHTML"' in partial
    assert 'name="tab" value="analytics"' in partial
    assert 'name="months" value="12"' in partial

    # На полной загрузке страницы тот же блок рендерится без OOB.
    page = client.get("/tutor/finance?tab=analytics&months=12").text
    assert 'id="finance-period-state"' in page
    assert "hx-swap-oob" not in page


def test_operations_refresh_url_keeps_tab_state(client, tutor_factory):
    """Перезапрос по `payment-saved` не сбрасывает вкладку и её состояние."""
    _login(client, tutor_factory)
    page = client.get("/tutor/finance?period=month&tab=analytics&months=12").text

    # `&` в атрибуте экранирован как `&amp;` — так и должно быть в HTML.
    assert (
        'hx-get="/tutor/finance/operations?period=month&amp;tab=analytics&amp;months=12"'
        in page
    )


def test_analytics_pills_load_partial_via_htmx(client, tutor_factory):
    """Пилюли 6/12 мес живут внутри секции — тоже грузятся htmx."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance?tab=analytics").text

    assert (
        'hx-get="/tutor/finance/tabs/analytics?period=month&months=12"' in html
    )
    # Ссылка остаётся обычным адресом страницы для работы без JS.
    assert 'href="/tutor/finance?period=month&tab=analytics&months=12"' in html


def test_forecast_month_form_loads_partial_via_htmx(client, tutor_factory):
    """Смена месяца прогноза подменяет секцию, а не перезагружает страницу."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance?tab=forecast").text

    assert 'hx-get="/tutor/finance/tabs/forecast"' in html
    assert 'action="/tutor/finance"' in html  # без JS форма шлёт на страницу


def test_tab_isolation_between_tutors(client, tutor_factory, student_factory):
    """Чужие операции не попадают в ответ ручки вкладки."""
    from app.database import SessionLocal
    from app.finance.models.account_operation import AccountOperation

    _login(client, tutor_factory)
    stranger = student_factory(first_name="Чужанин")
    with SessionLocal() as session:
        session.add(
            AccountOperation(
                student_id=stranger,
                kind="payment",
                amount=9999,
                occurred_at=utcnow(),
                status="paid",
                method="transfer",
            )
        )
        session.commit()

    body = client.get("/tutor/finance/tabs/all?period=all").text
    assert "Чужанин" not in body
    assert "9\u00a0999" not in body
