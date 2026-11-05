"""Тесты блока НПД на странице «Финансы» (change add-npd-tax-block).

Поведение проверяется тем же путём, что у пользователя: маршруты, поля
формы профиля и query-параметры страницы; разметка ищется по тексту и
атрибутам. Даты строятся от «сейчас» (зона репетитора в тестах — UTC).

Сценарии отражают пять пунктов ТЗ: блок налога с детализацией по
физлицам/юрлицам, налоговая строка и итог «с учётом налогов», карточка
«Чистая прибыль (после налогов)», подсказка про юрлиц, прогресс годового
лимита. Флаг выключен — страница выглядит как раньше.
"""

import re
from datetime import UTC, datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.models.expense import Expense
from app.tutor.models.tutor_settings import TutorSettings, default_values
from app.tutor.services.clock import utcnow

NBSP = "\u00a0"
MINUS = "\u2212"

PASSWORD = "Секретный-Пароль-1"


def _login(client, tutor_factory, email="npd@example.com", name="Самозанятый"):
    """Репетитор с зоной UTC и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _money(value: int) -> str:
    """«20 000 ₽» — как форматирует finance.presentation.money."""
    return f"{abs(value):,}".replace(",", NBSP) + NBSP + "₽"


def _balance(value: int) -> str:
    """Сумма со знаком: типографский минус у отрицательной."""
    return f"{MINUS}{_money(value)}" if value < 0 else _money(value)


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


def _expense(tutor_id: str, amount: int, when: datetime):
    """Расход репетитора напрямую в БД."""
    with SessionLocal() as session:
        session.add(
            Expense(
                tutor_id=tutor_id, amount=amount, category="rent", spent_at=when
            )
        )
        session.commit()


def _set_npd(tutor_id: str, **values):
    """Настройки НПД для репетитора (по умолчанию — включённый флаг)."""
    with SessionLocal() as session:
        row = session.get(TutorSettings, tutor_id)
        if row is None:
            row = TutorSettings(tutor_id=tutor_id, **default_values())
            session.add(row)
        row.is_npd_payer = True
        for name, value in values.items():
            setattr(row, name, value)
        session.commit()


def _lead_row(html: str) -> str:
    """Разметка главного яруса карточек (до компактного яруса)."""
    start = html.find('fin-kpis fin-kpis--lead')
    end = html.find('fin-kpis fin-kpis--secondary')
    assert start != -1 and end != -1, "нет главного яруса"
    return html[start:end]


def _kpi_value(html: str, title: str) -> str:
    """Значение карточки сводки по её заголовку."""
    match = re.search(
        rf'{re.escape(title)}</span>.*?fin-kpi__value[^"]*">\s*([^<]*?)\s*</p>',
        html,
        flags=re.S,
    )
    assert match, f"нет карточки «{title}»"
    return match.group(1)


def _npd_block(html: str) -> str:
    """Разметка блока НПД."""
    match = re.search(
        r'<section class="card fin-npd".*?</section>', html, flags=re.S
    )
    assert match, "нет блока НПД"
    return match.group(0)


def _compare_block(html: str) -> str:
    """Разметка блока «Заработано и получено»."""
    match = re.search(
        r'<section class="card fin-compare.*?</section>', html, flags=re.S
    )
    assert match, "нет блока сравнения"
    return match.group(0)


# ---------------------------------------------------------------------------
# Флаг выключен: страница не меняется
# ---------------------------------------------------------------------------


def test_npd_disabled_keeps_page_unchanged(client, tutor_factory, student_factory):
    """По умолчанию репетитор не самозанятый: блока налога нет."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    _operation(student_id, "lesson", 20000, utcnow())

    html = client.get("/tutor/finance").text
    assert "fin-npd" not in html
    assert "Налог на профессиональный доход" not in html
    assert "Чистая прибыль (после налогов)" not in html
    assert "Налог НПД" not in html
    # Прежний итог блока сравнения на месте.
    compare = _compare_block(html)
    assert "= Осталось репетитору" in compare
    assert "Чистая прибыль (с учётом налогов)" not in compare


def test_npd_disabled_three_lead_cards(client, tutor_factory):
    """При выключенном флаге главный ярус остаётся из трёх карточек."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance").text
    lead = _lead_row(html)
    assert lead.count('class="card fin-kpi fin-kpi--lead"') == 3


# ---------------------------------------------------------------------------
# Флаг включён: налог, детализация, карточка и итог
# ---------------------------------------------------------------------------


def test_npd_block_with_split_income(client, tutor_factory, student_factory):
    """Доход 20 000 от физлиц и 10 000 от юрлиц → налог 800 + 600 = 1 400."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    individual = student_factory(tutor_id=tutor_id, payer_type="individual")
    legal = student_factory(tutor_id=tutor_id, payer_type="legal_entity")
    now = utcnow()
    _operation(individual, "lesson", 20000, now)
    _operation(legal, "lesson", 10000, now)

    html = client.get("/tutor/finance").text
    block = _npd_block(html)
    assert "Итого налог к уплате" in block
    assert _money(1400) in block
    assert f"С физлиц (4{chr(0xa0)}%)" in block
    assert _money(800) in block
    assert f"С юрлиц (6{chr(0xa0)}%)" in block
    assert _money(600) in block
    assert "«Мой налог»" in block
    assert "налогового вычета" in block


def test_npd_card_net_after_tax(client, tutor_factory, student_factory):
    """Карточка «Чистая прибыль (после налогов)»: доход − расходы − налог."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    individual = student_factory(tutor_id=tutor_id, payer_type="individual")
    legal = student_factory(tutor_id=tutor_id, payer_type="legal_entity")
    now = utcnow()
    _operation(individual, "lesson", 20000, now)
    _operation(legal, "lesson", 10000, now)
    _expense(tutor_id, 5000, now)

    html = client.get("/tutor/finance").text
    # 30 000 − 5 000 − 1 400 = 23 600.
    assert _kpi_value(html, "Чистая прибыль (после налогов)") == _money(23600)
    assert "Прибыль с учётом НПД" in html


def test_npd_compare_block_tax_line(client, tutor_factory, student_factory):
    """Налоговая строка и новый итог блока сравнения (пример 20 000 − 5 000 − 1 000)."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    individual = student_factory(tutor_id=tutor_id, payer_type="individual")
    now = utcnow()
    # Ставка 5 % из настроек: 20 000 × 5 % = 1 000 — арифметика примера ТЗ.
    _set_npd(tutor_id, npd_rate_individual_bp=500)
    _operation(individual, "lesson", 20000, now)
    _expense(tutor_id, 5000, now)

    html = client.get("/tutor/finance").text
    compare = _compare_block(html)
    assert "− Налог НПД (расчётный)" in compare
    assert "С физлиц (5" in _npd_block(html)
    assert _money(1000) in compare
    assert "= Чистая прибыль (с учётом налогов)" in compare
    assert _balance(14000) in compare
    assert "= Осталось репетитору" not in compare


def test_npd_negative_net_after_tax(client, tutor_factory, student_factory):
    """Отрицательная чистая прибыль — типографский минус."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    individual = student_factory(tutor_id=tutor_id, payer_type="individual")
    now = utcnow()
    _operation(individual, "lesson", 1000, now)
    _expense(tutor_id, 2000, now)

    html = client.get("/tutor/finance").text
    # 1 000 − 2 000 − 40 = −1 040.
    assert _kpi_value(html, "Чистая прибыль (после налогов)") == _balance(-1040)


def test_npd_lead_row_has_four_cards(client, tutor_factory):
    """С включённым флагом в главном ярусе четыре карточки."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    html = client.get("/tutor/finance").text
    lead = _lead_row(html)
    assert lead.count('class="card fin-kpi fin-kpi--lead"') == 4
    # Новая карточка идёт после «Чистой прибыли», перед «Долгами».
    titles = re.findall(r'fin-kpi__title">([^<]+)<', lead)
    assert titles == [
        "Доход",
        "Чистая прибыль",
        "Долги учеников",
        "Чистая прибыль (после налогов)",
    ]


# ---------------------------------------------------------------------------
# Ставки и лимит из настроек
# ---------------------------------------------------------------------------


def test_npd_custom_rates(client, tutor_factory, student_factory):
    """Ставки 5 % / 7 % из настроек меняют расчёт без правок кода."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id, npd_rate_individual_bp=500, npd_rate_legal_bp=700)
    individual = student_factory(tutor_id=tutor_id, payer_type="individual")
    legal = student_factory(tutor_id=tutor_id, payer_type="legal_entity")
    now = utcnow()
    _operation(individual, "lesson", 10000, now)
    _operation(legal, "lesson", 10000, now)

    block = _npd_block(client.get("/tutor/finance").text)
    # 10 000 × 5 % = 500, 10 000 × 7 % = 700, итого 1 200.
    assert _money(1200) in block
    assert _money(500) in block
    assert _money(700) in block


def test_npd_custom_limit_warning(client, tutor_factory, student_factory):
    """Изменённый лимит 1 000 000 и доход с начала года — предупреждение."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id, npd_income_limit=1000000)
    student_id = student_factory(tutor_id=tutor_id)
    _operation(student_id, "lesson", 900000, utcnow())

    block = _npd_block(client.get("/tutor/finance").text)
    assert f"из {_money(1000000)} (90 %)" in block
    assert "приближается лимит дохода" in block
    assert "fin-npd__bar--warning" in block


def test_npd_limit_half_no_warning(client, tutor_factory, student_factory):
    """Доход 50 % лимита — шкала без предупреждения."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    _operation(student_id, "lesson", 1200000, utcnow())

    block = _npd_block(client.get("/tutor/finance").text)
    assert f"из {_money(2400000)} (50 %)" in block
    assert "приближается лимит дохода" not in block
    assert "fin-npd__bar--warning" not in block


def test_npd_limit_yearly_ignores_period(client, tutor_factory, student_factory):
    """Лимит считается по календарному году, а не по выбранному периоду."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id, npd_income_limit=1000000)
    student_id = student_factory(tutor_id=tutor_id)
    # Доход прошлого года в лимит не входит.
    _operation(student_id, "lesson", 800000, datetime(2020, 3, 1, 12, tzinfo=UTC))
    _operation(student_id, "lesson", 100000, utcnow())

    block = _npd_block(client.get("/tutor/finance?period=all").text)
    assert f"Доход с начала года: {_money(100000)}" in block


# ---------------------------------------------------------------------------
# Подсказка про юрлиц
# ---------------------------------------------------------------------------


def test_npd_legal_insight_when_legal_share_high(
    client, tutor_factory, student_factory
):
    """Доля юрлиц больше 30 % — подсказка про ставку 6 %."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    individual = student_factory(tutor_id=tutor_id, payer_type="individual")
    legal = student_factory(tutor_id=tutor_id, payer_type="legal_entity")
    now = utcnow()
    _operation(individual, "lesson", 6000, now)
    _operation(legal, "lesson", 4000, now)

    block = _npd_block(client.get("/tutor/finance").text)
    assert "Вы работаете с юрлицами по ставке 6" in block
    assert "Это на 2" in block


def test_npd_legal_insight_hidden_when_share_low(
    client, tutor_factory, student_factory
):
    """Доля юрлиц 20 % — подсказки нет."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    individual = student_factory(tutor_id=tutor_id, payer_type="individual")
    legal = student_factory(tutor_id=tutor_id, payer_type="legal_entity")
    now = utcnow()
    _operation(individual, "lesson", 8000, now)
    _operation(legal, "lesson", 2000, now)

    block = _npd_block(client.get("/tutor/finance").text)
    assert "Вы работаете с юрлицами" not in block


# ---------------------------------------------------------------------------
# Изоляция
# ---------------------------------------------------------------------------


def test_npd_isolated_between_tutors(client, tutor_factory, student_factory):
    """Чужой доход в налог вошедшего не попадает."""
    other_tutor = tutor_factory(name="Чужой", email="other-npd@example.com")
    _set_npd(other_tutor)
    other_student = student_factory(tutor_id=other_tutor, payer_type="legal_entity")
    _operation(other_student, "lesson", 500000, utcnow())

    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    own = student_factory(tutor_id=tutor_id, payer_type="individual")
    _operation(own, "lesson", 2000, utcnow())

    block = _npd_block(client.get("/tutor/finance").text)
    assert _money(80) in block
    assert _money(5000) not in block


# ---------------------------------------------------------------------------
# Партиал htmx: тот же контекст
# ---------------------------------------------------------------------------


def test_npd_summary_partial_has_block(client, tutor_factory, student_factory):
    """Партиал `/tutor/finance/summary` считает налог тем же кодом."""
    tutor_id = _login(client, tutor_factory)
    _set_npd(tutor_id)
    individual = student_factory(tutor_id=tutor_id, payer_type="individual")
    _operation(individual, "lesson", 20000, utcnow())

    response = client.get(
        "/tutor/finance/summary", headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert "fin-npd" in response.text
    assert _money(800) in response.text