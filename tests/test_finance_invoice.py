"""Счёт за период: расчёт и диалог (задачи 7.1–7.2).

Счёт — не операция: он ничего не сохраняет и не меняет баланс. Проверяется
и расчёт (`invoice_context`), и разметка диалога — период по умолчанию,
тумблер остатка, отсутствие урока без цены и неактивная кнопка отправки
(design D13, спека student-finance «Счёт за период»).

«Сегодня» в этом файле зафиксировано autouse-фикстурой `_frozen_today`
(24.10.2026), поэтому период по умолчанию — всегда ноябрь 2026, а литералы
дат в ассертах не зависят от дня запуска тестов.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.database import SessionLocal
from app.finance.services.balance import balance
from app.finance.services.invoice import (
    invoice_context,
    invoice_text,
    next_month_period,
    parse_period,
    priced_lessons,
)
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.models.tutor import Tutor

PASSWORD = "Секретный-Пароль-1"

# «Сегодня» для всего файла: период по умолчанию — следующий месяц, и без
# фиксации даты литералы 05–13.11.2026 рано или поздно выпадут из периода
# (тест, зелёный в октябре, краснеет в ноябре). Заморозка делает прогон
# независимым от дня запуска и сохраняет читаемые даты в ассертах.
TODAY = date(2026, 10, 24)


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    """Фиксирует «сегодня» в сервисе счёта: 24.10.2026 → период 01–30.11.2026."""
    from app.finance.services import invoice as module

    monkeypatch.setattr(module, "today_local", lambda tutor: TODAY)


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="invoice-owner@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "invoice-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def student_id(student_factory, owner):
    """Ученик вошедшего репетитора."""
    return student_factory(tutor_id=owner, first_name="Мария", last_name="Петрова")


def _student(session, student_id: str) -> Student:
    """Карточка ученика для сервиса счёта."""
    return session.get(Student, student_id)


def _lesson(
    session,
    *,
    student_id=None,
    group_id=None,
    price=1200,
    status="planned",
    starts_at=None,
) -> Lesson:
    """Урок напрямую в БД: счёту важен только период и цена."""
    lesson = Lesson(
        student_id=student_id,
        group_id=group_id,
        type="group" if group_id else "individual",
        starts_at=starts_at or datetime(2026, 11, 5, 10, 0, tzinfo=UTC),
        duration_min=60,
        price=price,
        status=status,
    )
    session.add(lesson)
    session.commit()
    return lesson


def _context(owner: str, student_id: str, **kwargs) -> dict:
    """Контекст счёта с периодом по умолчанию (ноябрь 2026 в UTC).

    Период задаёт не системная дата, а `_frozen_today`: «сегодня» — 24.10.2026.
    """
    with SessionLocal() as session:
        return invoice_context(
            session,
            _student(session, student_id),
            session.get(Tutor, owner),
            **kwargs,
        )


# --------------------------------------------------------------------------
# 7.1 Период и расчёт
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        pytest.param(
            date(2026, 12, 31),
            (date(2027, 1, 1), date(2027, 1, 31)),
            id="december-rolls-to-january",
        ),
        pytest.param(
            date(2026, 10, 24),
            (date(2026, 11, 1), date(2026, 11, 30)),
            id="full-next-month",
        ),
    ],
)
def test_next_month_period(today, expected, monkeypatch):
    """Период по умолчанию — весь следующий месяц, с переходом через год."""
    from app.finance.services import invoice as module

    monkeypatch.setattr(module, "today_local", lambda tutor: today)

    assert next_month_period(None) == expected

def test_parse_period_falls_back_to_default_on_garbage():
    """Опечатка в дате не роняет диалог: показывается период по умолчанию."""
    start, end, errors = parse_period("2026-13-45", "не дата", None)

    assert (start, end) == next_month_period(None)
    assert len(errors) == 2


def test_parse_period_rejects_reversed_range():
    """Начало позже окончания — период по умолчанию и сообщение."""
    start, end, errors = parse_period("2026-12-01", "2026-11-01", None)

    assert (start, end) == next_month_period(None)
    assert errors == ["Дата начала позже даты окончания — показан следующий месяц."]


def test_invoice_lists_individual_lessons_with_price(student_id):
    """Индивидуальный урок с ценой попадает в счёт со своей суммой."""
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200)
        _lesson(
            session,
            student_id=student_id,
            price=1500,
            starts_at=datetime(2026, 11, 12, 10, 0, tzinfo=UTC),
        )

        lines = priced_lessons(
            session, student_id, date(2026, 11, 1), date(2026, 11, 30), None
        )

    assert [line["price"] for line in lines] == [1200, 1500]
    assert [line["label"] for line in lines] == ["Урок", "Урок"]


def test_invoice_excludes_lessons_without_price(student_id):
    """Урок без цены в счёт не попадает: «0 ₽» выглядел бы как льгота."""
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=None)

        lines = priced_lessons(
            session, student_id, date(2026, 11, 1), date(2026, 11, 30), None
        )

    assert lines == []


def test_invoice_excludes_lessons_outside_period(student_id):
    """Урок за границей периода в счёт не входит."""
    with SessionLocal() as session:
        _lesson(
            session,
            student_id=student_id,
            starts_at=datetime(2026, 12, 1, 10, 0, tzinfo=UTC),
        )

        lines = priced_lessons(
            session, student_id, date(2026, 11, 1), date(2026, 11, 30), None
        )

    assert lines == []


def test_invoice_group_lesson_uses_member_price(
    student_id, group_factory, group_member_factory
):
    """Групповой урок: цена участника перекрывает общую цену группы."""
    group_id = group_factory(price_per_lesson=1500)
    group_member_factory(group_id=group_id, student_id=student_id, price_override=1000)

    with SessionLocal() as session:
        _lesson(session, group_id=group_id, price=None)

        lines = priced_lessons(
            session, student_id, date(2026, 11, 1), date(2026, 11, 30), None
        )

    assert [line["price"] for line in lines] == [1000]
    assert [line["label"] for line in lines] == ["Групповой урок"]


def test_invoice_group_without_price_is_skipped(
    student_id, group_factory, group_member_factory
):
    """Группа без цены и участник без своей цены — строки нет."""
    group_id = group_factory()
    group_member_factory(group_id=group_id, student_id=student_id)

    with SessionLocal() as session:
        _lesson(session, group_id=group_id, price=None)

        lines = priced_lessons(
            session, student_id, date(2026, 11, 1), date(2026, 11, 30), None
        )

    assert lines == []


def test_invoice_due_accounts_for_balance(owner, student_id, operation_factory):
    """К оплате = стоимость занятий − баланс (10 800 − 300 = 10 500)."""
    operation_factory(student_id=student_id, amount=300)
    with SessionLocal() as session:
        for day in range(5, 14):
            _lesson(
                session,
                student_id=student_id,
                price=1200,
                starts_at=datetime(2026, 11, day, 10, 0, tzinfo=UTC),
            )

    context = _context(owner, student_id)

    assert context["invoice_total"] == 10800
    assert context["invoice_balance"] == 300
    assert context["invoice_due"] == 10500


def test_invoice_due_without_balance_toggle(owner, student_id, operation_factory):
    """Тумблер выключен — к оплате равно стоимости занятий."""
    operation_factory(student_id=student_id, amount=300)
    with SessionLocal() as session:
        for day in range(5, 14):
            _lesson(
                session,
                student_id=student_id,
                price=1200,
                starts_at=datetime(2026, 11, day, 10, 0, tzinfo=UTC),
            )

    context = _context(owner, student_id, use_balance=False)

    assert context["invoice_due"] == 10800


def test_invoice_does_not_change_balance(owner, student_id, operation_factory):
    """Открытие счёта не создаёт операций: баланс остаётся прежним."""
    operation_factory(student_id=student_id, amount=2000)
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200)

    context = _context(owner, student_id)

    assert context["invoice_total"] == 1200
    with SessionLocal() as session:
        assert balance(session, student_id) == 2000


def test_invoice_text_contains_lines_and_due(owner, student_id):
    """Текст сообщения содержит занятие, стоимость и сумму к оплате."""
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200)

    context = _context(owner, student_id)
    text = context["invoice_text"]

    assert "05.11.2026, 10:00 — Урок — 1\u00a0200\u00a0₽" in text
    assert "Стоимость занятий: 1\u00a0200\u00a0₽" in text
    assert "К оплате: 1\u00a0200\u00a0₽" in text


def test_invoice_text_without_lessons_says_so():
    """Пустой период: в тексте нет ни строк, ни нулевых сумм."""
    text = invoice_text(
        date(2026, 11, 1),
        date(2026, 11, 30),
        [],
        0,
        0,
        0,
        True,
    )

    assert "Занятий в периоде нет." in text
    assert "К оплате" not in text


# --------------------------------------------------------------------------
# 7.2 Диалог
# --------------------------------------------------------------------------


def test_invoice_dialog_opens_with_default_period(client, student_id):
    """Диалог открывается на следующем месяце; поля «С» и «По» заполнены.

    Ожидания — литералы, а не повторный вызов `next_month_period`: иначе тест
    сверял бы функцию саму с собой и не заметил бы сдвиг периода по умолчанию.
    """
    response = client.get(f"/tutor/students/{student_id}/invoice")

    assert response.status_code == 200
    html = response.text
    assert "Счёт за период" in html
    assert 'value="2026-11-01"' in html
    assert 'value="2026-11-30"' in html


def test_invoice_dialog_shows_lesson_lines(client, student_id):
    """Строка занятия в разметке — дата, подпись и сумма."""
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200)

    html = client.get(f"/tutor/students/{student_id}/invoice").text

    assert "05.11.2026, 10:00" in html
    assert "1\u00a0200\u00a0₽" in html


def test_invoice_dialog_balance_toggle_changes_due(client, student_id, operation_factory):
    """`balance=0` в адресе убирает вычитание остатка из суммы к оплате."""
    operation_factory(student_id=student_id, amount=300)
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200)

    with_balance = client.get(f"/tutor/students/{student_id}/invoice").text
    without_balance = client.get(
        f"/tutor/students/{student_id}/invoice?balance=0"
    ).text

    assert "900\u00a0₽" in with_balance
    assert 'value="0"' in without_balance
    # При выключенном тумблере к оплате равно стоимости занятия.
    assert without_balance.count("1\u00a0200\u00a0₽") >= 2


def test_invoice_dialog_send_button_is_disabled(client, student_id):
    """«Отправить ученику» неактивна и не имеет ни адреса, ни `hx-*`."""
    html = client.get(f"/tutor/students/{student_id}/invoice").text

    start = html.index("Отправить ученику")
    tag_start = html.rindex("<button", 0, start)
    tag = html[tag_start : html.index(">", start) + 1]

    assert "disabled" in tag
    assert "hx-" not in tag
    assert "href" not in tag
    assert 'type="button"' in tag


def test_invoice_dialog_copy_button_carries_server_text(client, student_id):
    """Текст для буфера приходит готовым в `data-invoice-text`, без `hx-*`."""
    html = client.get(f"/tutor/students/{student_id}/invoice").text

    start = html.index("Скопировать текст")
    tag_start = html.rindex("<button", 0, start)
    tag = html[tag_start : html.index(">", start) + 1]

    assert "data-invoice-text=" in tag
    assert "hx-" not in tag
    assert "@click=\"copyInvoice($el)\"" in tag


def test_invoice_dialog_says_sending_is_not_connected(client, student_id):
    """Подпись не утверждает, что у ученика нет каналов связи."""
    html = client.get(f"/tutor/students/{student_id}/invoice").text

    assert "скопируйте текст и отправьте сами" in html


# --------------------------------------------------------------------------
# 7.3 Копирование текста в буфер
# --------------------------------------------------------------------------


def _payments_js() -> str:
    """Содержимое `payments.js` для статических проверок копирования."""
    return (
        Path(__file__).resolve().parent.parent / "app" / "static" / "payments.js"
    ).read_text(encoding="utf-8")


def test_copy_uses_clipboard_api_and_server_text():
    """Текст берётся из `data-invoice-text`, а не собирается в браузере."""
    js = _payments_js()

    assert "navigator.clipboard" in js
    assert "clipboard.writeText" in js
    assert "data-invoice-text" in js
    # Ни одной денежной формулы в JS: суммы приходят с сервера.
    assert "toLocaleString" not in js
    assert "₽" not in js


def test_copy_shows_toast():
    """Подтверждение копирования — тост `.cal-toast` из дизайн-системы."""
    js = _payments_js()

    assert "toastText" in js
    assert "toastOpen" in js
    assert "setTimeout" in js

    html = Path(__file__).resolve().parent.parent.joinpath(
        "app/finance/templates/finance/_invoice_dialog.html"
    ).read_text(encoding="utf-8")
    assert 'class="cal-toast"' in html


def test_copy_button_does_not_send_request(client, student_id):
    """Копирование — клиентское действие: запрос не уходит."""
    html = client.get(f"/tutor/students/{student_id}/invoice").text

    start = html.index("Скопировать текст")
    tag = html[html.rindex("<button", 0, start) : html.index(">", start) + 1]

    assert "hx-" not in tag
    assert "formaction" not in tag
    assert 'type="button"' in tag


def test_foreign_student_invoice_is_404(client, owner, tutor_factory, student_factory):
    """Счёт чужого ученика отвечает как несуществующий."""
    foreign_student_id = student_factory(tutor_id=tutor_factory())

    response = client.get(
        f"/tutor/students/{foreign_student_id}/invoice", follow_redirects=False
    )

    assert response.status_code == 404
