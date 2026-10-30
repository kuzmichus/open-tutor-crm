"""Тесты ленты «Все операций»: списания за уроки, фильтр `kind` и итоги
(change finance-all-operations).

Лента показывает все движения средств: платежи всех статусов, возвраты,
расходы и списания за проведённые уроки. Фильтр по виду операции — чипсы
над таблицей, состояние в адресе (`?kind=…`), работает без JS. Итоги
(«Приходы»/«Возвраты»/«Расходы»/«Чистый») — суммы отфильтрованного набора
до лимита ленты, без списаний за уроки.

Поведение проверяется тем же путём, что у пользователя: маршруты,
query-параметры и атрибуты разметки; сервис ленты — напрямую.
"""

import html as html_lib
import re
from datetime import UTC, datetime

from app.database import SessionLocal
from app.finance.services.operations_section import parse_finance_kind
from app.student.models.student import Student
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow

NBSP = "\u00a0"
MINUS = "\u2212"

PASSWORD = "Секретный-Пароль-1"


def _login(client, tutor_factory, email="feed@example.com", name="Лентовед"):
    """Репетитор с зоной UTC и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _money(value: int) -> str:
    """«6 400 ₽» — как форматирует finance.presentation.money."""
    return f"{abs(value):,}".replace(",", NBSP) + NBSP + "₽"


def _ops_section(html: str) -> str:
    """Разметка секции ленты — без карточки балансов и сводки."""
    match = re.search(r'<section class="card fin-ops".*?</section>', html, re.S)
    assert match, "нет секции операций"
    return match.group(0)


def test_parse_kind_defaults_and_garbage():
    """Мусор в `kind` — «Все», известный ключ проходит, пусто — «Все»."""
    assert parse_finance_kind({}) == "all"
    assert parse_finance_kind({"kind": "income"}) == "income"
    assert parse_finance_kind({"kind": "refund"}) == "refund"
    assert parse_finance_kind({"kind": "expense"}) == "expense"
    assert parse_finance_kind({"kind": "lesson"}) == "lesson"
    assert parse_finance_kind({"kind": "nonsense"}) == "all"


def _tutor(tutor_id: str):
    with SessionLocal() as session:
        return session.get(Tutor, tutor_id)


def test_feed_totals_of_all_kinds(tutor_factory, student_factory, operation_factory):
    """Сценарий «Итоги на „Все операциях"»: 6 400 / 500 / 12 600 / −6 700."""
    from app.finance.models.expense import Expense
    from app.finance.services.operations_feed import operations_feed

    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    operation_factory(student_id=student_id, amount=6400, occurred_at=now)
    operation_factory(
        student_id=student_id, kind="refund", amount=500, occurred_at=now
    )
    operation_factory(
        student_id=student_id, kind="lesson", amount=800, occurred_at=now
    )
    with SessionLocal() as session:
        session.add(
            Expense(tutor_id=tutor_id, amount=12600, category="rent", spent_at=now)
        )
        session.commit()

    with SessionLocal() as session:
        feed = operations_feed(
            session,
            tutor_id,
            _tutor(tutor_id),
            tab="all",
            kind="all",
            start=None,
            end=None,
        )

    # Четыре строки: платёж, возврат, расход и списание за урок.
    assert len(feed["rows"]) == 4
    # Списание за урок в итоги не входит: это движение баланса ученика.
    assert feed["income"] == 6400
    assert feed["refund"] == 500
    assert feed["expense"] == 12600
    assert feed["net"] == 6400 - 500 - 12600 == -6700


def test_feed_kind_filters_narrow_rows(
    tutor_factory, student_factory, operation_factory
):
    """Каждый чип оставляет только свой вид операций и обнуляет прочие итоги."""
    from app.finance.models.expense import Expense
    from app.finance.services.operations_feed import operations_feed

    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    operation_factory(student_id=student_id, amount=6400, occurred_at=now)
    operation_factory(
        student_id=student_id, kind="refund", amount=500, occurred_at=now
    )
    operation_factory(
        student_id=student_id, kind="lesson", amount=800, occurred_at=now
    )
    with SessionLocal() as session:
        session.add(
            Expense(tutor_id=tutor_id, amount=12600, category="rent", spent_at=now)
        )
        session.commit()

    with SessionLocal() as session:
        tutor = _tutor(tutor_id)
        by_kind = {
            key: operations_feed(
                session, tutor_id, tutor, tab="all", kind=key, start=None, end=None
            )
            for key in ("income", "refund", "expense", "lesson")
        }

    directions = {
        key: sorted(row["direction"] for row in feed["rows"])
        for key, feed in by_kind.items()
    }
    assert directions["income"] == ["payment"]
    assert directions["refund"] == ["refund"]
    assert directions["expense"] == ["expense"]
    assert directions["lesson"] == ["lesson"]

    # Итоги следуют фильтру: «Расходы» — сумма трат, приходы и возвраты — нули.
    assert by_kind["expense"]["expense"] == 12600
    assert by_kind["expense"]["income"] == 0
    assert by_kind["expense"]["refund"] == 0
    assert by_kind["lesson"]["rows"][0]["amount_value"] == 800
    assert by_kind["lesson"]["income"] == 0


def test_lesson_row_in_feed(client, tutor_factory, student_factory, lesson_factory,
                            operation_factory):
    """Сценарий «Списание за урок в ленте»: дата урока, «Урок», ученик, минус."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id, first_name="Гриша")
    lesson_id = lesson_factory(
        student_id=student_id,
        note="тема: дроби",
        starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
    )
    operation_factory(
        student_id=student_id,
        kind="lesson",
        amount=1200,
        lesson_id=lesson_id,
        occurred_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
    )

    html = client.get("/tutor/finance?period=all&tab=all").text
    ops = _ops_section(html)
    assert "Гриша" in ops
    assert "Урок" in ops
    # Подпись — тип урока и заметка.
    assert "Индивидуальный" in ops
    assert "тема: дроби" in ops
    # Списание уменьшает баланс ученика: красная сумма со знаком «−».
    assert f"{MINUS}{_money(1200)}" in ops
    assert re.search(r'data-lucide="book-open"', ops)


def test_table_columns_and_pending_badge(client, tutor_factory, student_factory,
                                         operation_factory):
    """Колонки Дата/Тип/Описание/Сумма; «Ожидает» — бейджем рядом с типом."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id, first_name="Дана")
    operation_factory(
        student_id=student_id,
        amount=2400,
        status="pending",
        method="card",
        occurred_at=utcnow(),
    )

    html = client.get("/tutor/finance?period=all").text
    ops = _ops_section(html)
    assert ">Дата</th>" in ops
    assert ">Тип</th>" in ops
    assert ">Описание</th>" in ops
    assert ">Сумма</th>" in ops
    # Отдельной колонки «Статус» больше нет; статус платежа — бейдж в «Типе».
    assert ">Статус</th>" not in ops
    assert re.search(
        r'fin-ops__cell--type">[^<]*<span class="fin-ops__status '
        r'fin-ops__status--pending">Ожидает</span>',
        ops,
    )
    assert "Дана" in ops


def test_kind_chips_markup_and_active_state(client, tutor_factory):
    """Чипсы фильтра: пять видов, активный по `kind`, href работает без JS."""
    _login(client, tutor_factory)

    html = client.get("/tutor/finance?period=all&tab=all").text
    for label in ("Все", "Приходы", "Возвраты", "Расходы", "Списания за уроки"):
        assert label in html
    for key in ("income", "refund", "expense", "lesson"):
        assert f'href="/tutor/finance?period=all&amp;tab=all&amp;kind={key}"' in html
    # Активный чип по умолчанию — «Все».
    assert re.search(r'fin-ops__chip fin-ops__chip--active"[^>]*>?\s*Все', html)

    income = client.get("/tutor/finance?period=all&tab=all&kind=income").text
    assert re.search(
        r'fin-ops__chip fin-ops__chip--active"[^>]*>?\s*Приходы', income
    )
    # hx-get чипса — на ручку вкладки с тем же фильтром; состояние в адресе.
    assert 'hx-get="/tutor/finance/tabs/all?period=all&amp;kind=income"' in income

    # Фильтр только у «Все операций»: на «Расходах» чипсов нет.
    expenses = client.get("/tutor/finance?period=all&tab=expenses").text
    assert "fin-ops__chip" not in expenses

    # Без JS чип — обычная ссылка на страницу (href уже проверен выше).
    unescaped = html_lib.unescape(income)
    assert 'href="/tutor/finance?period=all&tab=all&kind=income"' in unescaped


def test_totals_cards_on_page(client, tutor_factory, student_factory,
                              operation_factory):
    """Сценарий «Итоги на „Все операциях"» через HTTP: карточки над таблицей."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id, first_name="Ева")
    now = utcnow()
    operation_factory(student_id=student_id, amount=6400, occurred_at=now)
    operation_factory(student_id=student_id, kind="refund", amount=500,
                      occurred_at=now)
    from app.finance.models.expense import Expense

    with SessionLocal() as session:
        session.add(
            Expense(
                tutor_id=tutor_id, amount=12600, category="rent", spent_at=now
            )
        )
        session.commit()

    html = client.get("/tutor/finance?period=all&tab=all").text
    ops = _ops_section(html)
    assert "Приходы" in ops and f"{_money(6400)}" in ops
    assert "Возвраты" in ops and f"{_money(500)}" in ops
    assert "Расходы" in ops and f"{_money(12600)}" in ops
    # Чистый отрицательный — с типографским минусом и красным классом.
    assert f"{MINUS}{_money(6700)}" in ops
    net = re.search(
        r"Чистый.*?fin-ops__total-value([^\"]*)\">([^<]*)<", ops, flags=re.S
    )
    assert net, "нет карточки «Чистый»"
    assert "fin-ops__total-value--red" in net.group(1)

    # Итоги следуют фильтру: чип «Расходы» — приходы и возвраты в нулях.
    filtered = _ops_section(
        client.get("/tutor/finance?period=all&tab=all&kind=expense").text
    )
    assert f"{_money(12600)}" in filtered
    assert f"+{_money(6400)}" not in filtered


def test_add_button_near_tabs(client, tutor_factory):
    """Кнопка «Добавить» — на лента-вкладках, и её нет на графиках/прогнозе."""
    _login(client, tutor_factory)

    for tab in ("all", "expenses", "income"):
        html = client.get(f"/tutor/finance?period=all&tab={tab}").text
        assert 'hx-get="/tutor/expenses/new"' in html
        assert 'hx-target="#modal-expense"' in html
        assert "Добавить" in html

    for tab in ("analytics", "forecast"):
        html = client.get(f"/tutor/finance?period=all&tab={tab}").text
        section = re.search(r'id="finance-operations".*?fin-operations__layout',
                            html, re.S)
        assert section, "нет секции операций"
        assert "/tutor/expenses/new" not in section.group(0)


def test_refresh_keeps_kind_filter(client, tutor_factory):
    """Перезапрос секции по сохранению отвечает тем же фильтром `kind`."""
    _login(client, tutor_factory)
    html = client.get(
        "/tutor/finance/operations?period=all&tab=all&kind=expense"
    ).text
    # Активный чип сохранён, перезапрос по событию едет с тем же kind.
    assert re.search(r'fin-ops__chip fin-ops__chip--active"[^>]*>?\s*Расходы', html)
    assert (
        'hx-get="/tutor/finance/operations?period=all&amp;tab=all&amp;kind=expense"'
        in html
    )
    assert 'hx-trigger="payment-saved from:body, expense-saved from:body"' in html

    # Ручка вкладки тоже сохраняет фильтр и отдаёт канонический адрес.
    partial = client.get("/tutor/finance/tabs/all?period=all&kind=income")
    assert partial.headers["HX-Push-Url"] == (
        "/tutor/finance?period=all&tab=all&kind=income"
    )


def test_period_change_keeps_kind(client, tutor_factory):
    """Смена периода не сбрасывает чип: форма периода несёт `kind`."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance?period=month&tab=all&kind=refund").text
    assert 'name="kind" value="refund"' in html


def test_isolation_rows_and_totals(client, tutor_factory, student_factory,
                                   operation_factory):
    """Чужие списания, платежи и расходы не видны ни в строках, ни в итогах."""
    _login(client, tutor_factory)
    stranger_student = student_factory(first_name="Жора", last_name="Чужой")
    with SessionLocal() as session:
        # Владелец ученика — репетитор, создавший его; у Expense владелец
        # задаётся колонкой tutor_id, берём его у «чужого» ученика.
        stranger_tutor_id = session.get(Student, stranger_student).tutor_id

    now = utcnow()
    operation_factory(
        student_id=stranger_student,
        amount=9100,
        status="paid",
        method="transfer",
        occurred_at=now,
    )
    operation_factory(
        student_id=stranger_student, kind="lesson", amount=1300, occurred_at=now
    )
    from app.finance.models.expense import Expense

    with SessionLocal() as session:
        session.add(
            Expense(
                tutor_id=stranger_tutor_id,
                amount=7700,
                category="rent",
                spent_at=now,
            )
        )
        session.commit()

    html = client.get("/tutor/finance?period=all&tab=all").text
    ops = _ops_section(html)
    assert "Жора" not in ops
    assert "Чужой" not in ops
    assert f"+{_money(9100)}" not in ops
    assert f"{MINUS}{_money(1300)}" not in ops
    assert f"{MINUS}{_money(7700)}" not in ops

    # Итоги тоже чистые: чужих денег в карточках нет.
    totals = re.search(
        r'class="fin-ops__totals".*?(?=<table|<div class="fin-ops__empty)',
        ops,
        flags=re.S,
    )
    assert totals, "нет блока итогов"
    assert f"{_money(9100)}" not in totals.group(0)
    assert f"{_money(7700)}" not in totals.group(0)
