"""Тесты вкладки «Аналитика» страницы финансов (графики по референсу).

Поведение проверяется тем же путём, что у пользователя: те же маршруты и
query-параметры; разметка ищется по тексту, классам и атрибутам. Геометрию
SVG считает сервис — тестам достаточно классов столбцов, подписей месяцев
и делений оси, браузер не нужен.

Сценарии: пилюли горизонта 6/12 мес, три ряда столбцов (доход — только
оплаченные платежи, заработано — списания за уроки, расходы — траты),
пирог категорий с долями, пустые состояния и изоляция по репетитору.
"""

import re
from datetime import UTC, timedelta

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.models.expense import Expense
from app.tutor.services.clock import utcnow

NBSP = "\u00a0"

PASSWORD = "Секретный-Пароль-2"

# Короткие месяцы в именительном падеже — подписи оси X (как в сервисе).
_MONTHS_NOMINATIVE = (
    "Янв",
    "Фев",
    "Мар",
    "Апр",
    "Май",
    "Июн",
    "Июл",
    "Авг",
    "Сен",
    "Окт",
    "Ноя",
    "Дек",
)


def _login(client, tutor_factory, email="analyst@example.com", name="Аналитик"):
    """Репетитор с зоной UTC (заводское умолчание) и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _operation(student_id: str, kind: str, amount: int, when, **extra):
    """Операция счёта напрямую в БД (для графиков важен факт строки)."""
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


def _expense(tutor_id: str, amount: int, when, category: str = "rent", **extra):
    """Расход напрямую в БД."""
    with SessionLocal() as session:
        session.add(
            Expense(
                tutor_id=tutor_id,
                amount=amount,
                category=category,
                spent_at=when,
                **extra,
            )
        )
        session.commit()


def _analytics_section(html: str) -> str:
    """Разметка вкладки «Аналитика» — без сводки и карточки балансов.

    Суммы и категории легитимно встречаются в других секциях страницы,
    поэтому проверки графиков смотрят только свою секцию.
    """
    match = re.search(
        r'<section class="fin-analytics".*?</section>\s*</section>',
        html,
        flags=re.S,
    )
    assert match, "нет секции аналитики"
    return match.group(0)


def test_analytics_tab_shows_charts_and_pills(client, tutor_factory, student_factory):
    """Вкладка больше не заглушка: пилюли горизонта и две карточки графиков."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")
    now = utcnow()
    _operation(payer, "payment", 3000, now, status="paid", method="transfer")
    _expense(tutor_id, 1500, now, category="ads")

    html = client.get("/tutor/finance?tab=analytics").text
    section = _analytics_section(html)

    assert "Раздел в разработке" not in section
    assert "Доходы и расходы по месяцам" in section
    assert "Расходы по категориям" in section

    # Пилюли горизонта: 6 мес активна по умолчанию, 12 — ссылка с периодом.
    assert "6 мес" in section
    assert re.search(
        r'class="fin-pill fin-pill--active"[^>]*href="/tutor/finance\?period=month&tab=analytics&months=6"',
        section,
    )
    assert (
        'href="/tutor/finance?period=month&tab=analytics&months=12"' in section
    )

    # Легенда рядов и подписи делений оси — как на референсе.
    for label in ("Доход", "Заработано", "Расходы"):
        assert label in section
    assert "<svg" in section


def test_analytics_bars_draw_series_and_ticks(
    client, tutor_factory, student_factory
):
    """Три ряда столбцов; верхняя подпись оси — круглое «красивое» число."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")
    now = utcnow()

    _operation(payer, "payment", 30000, now, status="paid", method="card")
    _operation(payer, "lesson", 5000, now)
    _expense(tutor_id, 10000, now, category="ads")

    section = _analytics_section(client.get("/tutor/finance?tab=analytics").text)

    for series in ("income", "earned", "expenses"):
        assert f'class="fin-bar fin-bar--{series}"' in section

    # Максимум 30 000 → деления 0…30 000 шагом 10 000: верхняя подпись
    # круглым числом с неразрывным пробелом.
    assert f"30{NBSP}000" in section
    assert f"10{NBSP}000" in section

    # Подпись текущего месяца — короткий именительный падеж.
    assert _MONTHS_NOMINATIVE[now.month - 1] in section


def test_analytics_bars_cover_previous_month(client, tutor_factory, student_factory):
    """Платёж прошлого месяца рисуется своим столбцом, а не только текущим."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")

    prev_month = (utcnow().replace(day=1) - timedelta(days=1)).replace(
        day=1, hour=12, tzinfo=UTC
    )
    _operation(payer, "payment", 2000, prev_month, status="paid", method="card")
    _operation(payer, "payment", 3000, utcnow(), status="paid", method="card")

    section = _analytics_section(client.get("/tutor/finance?tab=analytics").text)

    income_bars = section.count('fin-bar--income"')
    assert income_bars == 2
    # Оба месяца подписаны на оси.
    assert _MONTHS_NOMINATIVE[prev_month.month - 1] in section
    assert _MONTHS_NOMINATIVE[utcnow().month - 1] in section


def test_analytics_pending_payment_not_drawn(client, tutor_factory, student_factory):
    """Ожидающий платёж — обещание, а не деньги: график остаётся пустым."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")
    _operation(payer, "payment", 5000, utcnow(), status="pending", method="card")

    section = _analytics_section(client.get("/tutor/finance?tab=analytics").text)
    assert "За выбранный период операций нет" in section
    # SVG в секции нет (логотип в сайдбаре — не в счёт).
    assert "<svg" not in section


def test_analytics_months_switch(client, tutor_factory, student_factory):
    """`months=12` — двенадцать групп, мусор и умолчание — шесть."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")
    _operation(payer, "payment", 1000, utcnow(), status="paid", method="card")

    default = _analytics_section(client.get("/tutor/finance?tab=analytics").text)
    assert default.count('class="fin-month"') == 6

    year = _analytics_section(
        client.get("/tutor/finance?tab=analytics&months=12").text
    )
    assert year.count('class="fin-month"') == 12
    assert 'class="fin-pill fin-pill--active"' in year

    garbage = _analytics_section(
        client.get("/tutor/finance?tab=analytics&months=99").text
    )
    assert garbage.count('class="fin-month"') == 6


def test_analytics_period_switch_keeps_months(client, tutor_factory, student_factory):
    """Смена периода сводки на вкладке не сбрасывает горизонт — скрытое поле."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")
    _operation(payer, "payment", 1000, utcnow(), status="paid", method="card")

    html = client.get("/tutor/finance?tab=analytics&months=12").text
    assert 'name="months" value="12"' in html

    # На других вкладках поля нет: горизонт — состояние только «Аналитики».
    plain = client.get("/tutor/finance?tab=all").text
    assert 'name="months"' not in plain


def test_analytics_categories_shares(client, tutor_factory):
    """Пирог: доли категорий с округлением до целых процентов и суммы."""
    tutor_id = _login(client, tutor_factory)
    now = utcnow()
    _expense(tutor_id, 3000, now, category="ads")
    _expense(tutor_id, 1000, now, category="transport")

    section = _analytics_section(client.get("/tutor/finance?tab=analytics").text)

    # Категории в легенде с долями и суммами; больший сектор — первым.
    assert re.search(r"Реклама</span>\s*<span class=\"fin-cat-legend__percent\">75%", section)
    assert re.search(r"Транспорт</span>\s*<span class=\"fin-cat-legend__percent\">25%", section)
    assert f"3{NBSP}000{NBSP}₽" in section
    assert "75%" in section
    assert "25%" in section
    # Сектора пирога и подписи долей снаружи.
    assert 'class="fin-slice fin-slice--7"' in section  # ads — индекс списка
    assert 'class="fin-slice fin-slice--9"' in section  # transport


def test_analytics_single_category_full_pie(client, tutor_factory):
    """Единственная категория — целый круг (дуга 360° не вырождается)."""
    tutor_id = _login(client, tutor_factory)
    _expense(tutor_id, 2500, utcnow(), category="software")

    section = _analytics_section(client.get("/tutor/finance?tab=analytics").text)
    assert 'class="fin-slice fin-slice--5"' in section
    assert "100%" in section
    assert "Программное обеспечение" in section


def test_analytics_no_expenses_pie_empty_bars_drawn(
    client, tutor_factory, student_factory
):
    """Без трат пирог пуст, столбцы рисуются: карточки независимы."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")
    _operation(payer, "payment", 2000, utcnow(), status="paid", method="card")

    html = client.get("/tutor/finance?tab=analytics").text
    assert "Расходов за выбранный период нет" in html
    assert 'fin-bar--income"' in html


def test_analytics_isolation_by_tutor(
    client, tutor_factory, student_factory
):
    """Чужие платежи и категории не попадают в графики вошедшего репетитора."""
    tutor_id = _login(client, tutor_factory)
    mine = student_factory(tutor_id=tutor_id, first_name="Аня")
    _operation(mine, "payment", 1000, utcnow(), status="paid", method="card")

    stranger_id = tutor_factory(name="Чужой", email="stranger@example.com")
    stranger_student = student_factory(tutor_id=stranger_id, first_name="Никита")
    _operation(
        stranger_student, "payment", 40000, utcnow(), status="paid", method="card"
    )
    _expense(stranger_id, 5000, utcnow(), category="rent")

    html = client.get("/tutor/finance?tab=analytics").text
    # Масштаб оси не подтянут под чужие 40 000, чужая категория не названа.
    assert f"40{NBSP}000" not in html
    assert "Аренда" not in _analytics_section(html)
    # Свой платёж нарисован.
    assert 'fin-bar--income"' in html


def test_analytics_partial_refresh_endpoint(client, tutor_factory, student_factory):
    """Партиал `/tutor/finance/operations` тоже строит аналитику —
    секция перезапрашивается по `payment-saved`/`expense-saved`."""
    tutor_id = _login(client, tutor_factory)
    payer = student_factory(tutor_id=tutor_id, first_name="Аня")
    _operation(payer, "payment", 1000, utcnow(), status="paid", method="card")

    partial = client.get(
        "/tutor/finance/operations?period=month&tab=analytics&months=12"
    ).text
    assert 'id="finance-operations"' in partial
    assert "Доходы и расходы по месяцам" in partial
    assert 'class="fin-month"' in partial
