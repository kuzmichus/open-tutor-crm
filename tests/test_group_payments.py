"""Вкладка «Оплаты» модалки управления группой: сводка, периоды, изоляция.

Панель приходит отдельным GET-маршрутом `/tutor/groups/{id}/payments`
(партиал с корнем `#group-payments-content`), поэтому поведение
проверяется по этому маршруту тем же путём, что у пользователя:
чипы периода — параметром `?period=`, разметка — по тексту сумм.

Тесты кладут операции явно (`operation_factory` с `occurred_at`),
потому что списания создаются только путями записи урока, а периоды
должны не зависеть от даты прогона.
"""

import re
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.finance.services.group_panel import normalize_period, period_bounds
from app.finance.services.presentation import balance_label, money

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="group-payments@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "group-payments@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _month_dates() -> tuple[datetime, datetime]:
    """Моменты внутри текущего и прошлого месяца по часам UTC.

    «Сейчас» всегда внутри текущего месяца (зона педагога в тестах —
    UTC), полдень дня перед первым числом — всегда в предыдущем: тесты
    не зависят ни от даты прогона, ни от локальной зоны сервера.
    """
    now = datetime.now(UTC)
    first_of_month = now.date().replace(day=1)
    last_month_day = first_of_month - timedelta(days=1)
    last_month = datetime(
        last_month_day.year, last_month_day.month, last_month_day.day, 12, 0, tzinfo=UTC
    )
    return now, last_month


def _charge(operation_factory, student_id, lesson_id, amount=1200, **extra):
    """Списание за групповой урок — строка счёта `kind='lesson'`."""
    return operation_factory(
        student_id=student_id,
        kind="lesson",
        amount=amount,
        lesson_id=lesson_id,
        status=None,
        method=None,
        **extra,
    )


# --------------------------------------------------------------------------
# Сервис: периоды
# --------------------------------------------------------------------------


def test_normalize_period_falls_back_to_all():
    """Неизвестное значение query — «За всё время», а не ошибка."""
    assert normalize_period(None) == "all"
    assert normalize_period("") == "all"
    assert normalize_period("взлом") == "all"
    assert normalize_period("this_month") == "this_month"


def test_period_bounds_this_month(monkeypatch):
    """«Этот месяц» — с первого числа 00:00 по первое число следующего."""
    from types import SimpleNamespace

    from app.finance.services import group_panel as module

    tutor = SimpleNamespace(timezone="UTC")
    monkeypatch.setattr(module, "today_local", lambda tutor: date(2026, 10, 24))
    start, end = period_bounds("this_month", tutor)

    assert start == datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 1, 0, 0, tzinfo=UTC)


def test_period_bounds_last_month_rolls_over_year(monkeypatch):
    """«Прошлый месяц» в январе — декабрь предыдущего года."""
    from app.finance.services import group_panel as module

    tutor = SimpleNamespace(timezone="UTC")
    monkeypatch.setattr(module, "today_local", lambda tutor: date(2027, 1, 9))
    start, end = period_bounds("last_month", tutor)

    assert start == datetime(2026, 12, 1, 0, 0, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, 0, 0, tzinfo=UTC)


def test_period_bounds_all_has_no_bounds():
    """«За всё время» — фильтра нет вовсе, а не «от нуля»."""
    assert period_bounds("all", SimpleNamespace(timezone="UTC")) == (None, None)


# --------------------------------------------------------------------------
# Сводка по референсу
# --------------------------------------------------------------------------


def test_panel_shows_group_charges_and_member_rows(
    owner,
    client,
    group_factory,
    group_member_factory,
    student_factory,
    lesson_factory,
    operation_factory,
):
    """Сводка сходится со строками: списания за групповые уроки, долг, баланс.

    Референс: два участника, каждому списано 1 200 ₽ за занятие группы,
    у обоих минусовые балансы — «Долг участников сейчас» 2 220 ₽.
    """
    group_id = group_factory(tutor_id=owner, name="Группа А", price_per_lesson=1200)
    first = student_factory(tutor_id=owner, first_name="Иван", last_name="Иванов")
    second = student_factory(tutor_id=owner, first_name="Ивана", last_name="Иванова")
    group_member_factory(group_id=group_id, student_id=first)
    group_member_factory(group_id=group_id, student_id=second)

    this_month, _ = _month_dates()
    lesson_one = lesson_factory(group_id=group_id, price=None)
    lesson_two = lesson_factory(group_id=group_id, price=None)
    _charge(operation_factory, first, lesson_one, occurred_at=this_month)
    _charge(operation_factory, second, lesson_two, occurred_at=this_month)

    response = client.get(f"/tutor/groups/{group_id}/payments")

    assert response.status_code == 200
    text = response.text
    assert "Списано за занятия группы" in text
    assert money(2400) in text
    assert "Возвращено" in text
    assert money(0) in text
    assert "Долг участников сейчас" in text
    assert money(2400) in text  # долг = 1200 + 1200
    # Строки участников: баланс со знаком, списание с числом занятий.
    assert "Иван Иванов" in text
    assert f"Баланс: {balance_label(-1200)}" in text
    assert f"Списано: {money(1200)} (1 занятие)" in text


def test_panel_member_links_to_student_payments(
    owner,
    client,
    group_factory,
    group_member_factory,
    student_factory,
):
    """Имя участника — ссылка в карточку ученика сразу на «Платежи»."""
    group_id = group_factory(tutor_id=owner)
    student_id = student_factory(tutor_id=owner, first_name="Мария")
    group_member_factory(group_id=group_id, student_id=student_id)

    response = client.get(f"/tutor/groups/{group_id}/payments")

    assert response.status_code == 200
    assert f'href="/tutor/students/{student_id}?tab=payments"' in response.text
    # Подпись-пояснение под списком.
    assert "Баланс и долг — по всем занятиям ученика" in response.text


def test_panel_counts_only_group_lessons_in_charged(
    owner,
    client,
    group_factory,
    group_member_factory,
    student_factory,
    lesson_factory,
    operation_factory,
):
    """Индивидуальные уроки участника в «Списано» по группе не попадают.

    В «Баланс» они входят (он по всему счёту ученика), в списание за
    занятия группы — нет: сводка отвечает за группу.
    """
    group_id = group_factory(tutor_id=owner)
    student_id = student_factory(tutor_id=owner, first_name="Мария")
    group_member_factory(group_id=group_id, student_id=student_id)

    this_month, _ = _month_dates()
    group_lesson = lesson_factory(group_id=group_id, price=None)
    individual_lesson = lesson_factory(student_id=student_id)
    _charge(operation_factory, student_id, group_lesson, occurred_at=this_month)
    # Списание за индивидуальный урок: тот же ученик, чужой для группы урок.
    _charge(
        operation_factory,
        student_id,
        individual_lesson,
        amount=500,
        occurred_at=this_month,
    )
    operation_factory(
        student_id=student_id,
        amount=500,
        occurred_at=this_month,
    )  # платёж

    response = client.get(f"/tutor/groups/{group_id}/payments")

    assert f"Списано: {money(1200)} (1 занятие)" in response.text
    assert "Списано: 1\u00a0700" not in response.text
    # Баланс: −1200 (группа) − 500 (индивидуал) + 500 (платёж) = −1200.
    assert f"Баланс: {balance_label(-1200)}" in response.text


def test_panel_refunds_scoped_to_members(
    owner,
    client,
    group_factory,
    group_member_factory,
    student_factory,
    operation_factory,
):
    """«Возвращено» — только возвраты участников группы."""
    group_id = group_factory(tutor_id=owner)
    member = student_factory(tutor_id=owner, first_name="Участник")
    outsider = student_factory(tutor_id=owner, first_name="Посторонний")
    group_member_factory(group_id=group_id, student_id=member)

    this_month, _ = _month_dates()
    operation_factory(
        student_id=member, kind="refund", amount=300, status=None, method=None,
        occurred_at=this_month,
    )
    operation_factory(
        student_id=outsider, kind="refund", amount=700, status=None, method=None,
        occurred_at=this_month,
    )

    response = client.get(f"/tutor/groups/{group_id}/payments")

    assert money(300) in response.text
    assert "700" not in response.text


# --------------------------------------------------------------------------
# Периоды
# --------------------------------------------------------------------------


def test_panel_period_filter(
    owner,
    client,
    group_factory,
    group_member_factory,
    student_factory,
    lesson_factory,
    operation_factory,
):
    """Чипы периода пересчитывают списания, но не долг.

    Занятия были в текущем и в прошлом месяце: «За всё время» видит оба,
    «Этот месяц» и «Прошлый месяц» — по одному, «Долг участников сейчас»
    одинаков во всех периодах.
    """
    group_id = group_factory(tutor_id=owner, price_per_lesson=1200)
    student_id = student_factory(tutor_id=owner, first_name="Мария")
    group_member_factory(group_id=group_id, student_id=student_id)

    this_month, last_month = _month_dates()
    lesson_this = lesson_factory(group_id=group_id, price=None)
    lesson_last = lesson_factory(group_id=group_id, price=None)
    _charge(operation_factory, student_id, lesson_this, occurred_at=this_month)
    _charge(operation_factory, student_id, lesson_last, occurred_at=last_month)
    operation_factory(
        student_id=student_id, kind="refund", amount=400, status=None,
        method=None, occurred_at=last_month,
    )

    all_time = client.get(f"/tutor/groups/{group_id}/payments").text
    this = client.get(f"/tutor/groups/{group_id}/payments?period=this_month").text
    last = client.get(f"/tutor/groups/{group_id}/payments?period=last_month").text

    assert f"Списано: {money(2400)} (2 занятия)" in all_time
    assert f"Списано: {money(1200)} (1 занятие)" in this
    assert f"Списано: {money(1200)} (1 занятие)" in last
    # Возврат прошлого месяца виден только в соответствующих периодах:
    # в «Этом месяце» возвращённых нет вовсе.
    assert "400" not in this
    assert money(400) in last
    assert f"Долг: {money(2800)}" in all_time  # баланс = −400 (возврат) − 2400 (списания)
    # Долг «сейчас» от периода не зависит.
    for text in (all_time, this, last):
        assert "Долг участников сейчас" in text
        assert money(2800) in text


def test_panel_active_chip_follows_period(owner, client, group_factory):
    """Активный чип рисует сервер: `?period=last_month` отмечен в разметке."""
    group_id = group_factory(tutor_id=owner)

    default = client.get(f"/tutor/groups/{group_id}/payments").text
    last = client.get(f"/tutor/groups/{group_id}/payments?period=last_month").text

    # Отмечено то значение, что пришло параметром; остальные — нет.
    assert re.search(r'value="all"\s+checked', default)
    assert not re.search(r'value="last_month"\s+checked', default)
    assert re.search(r'value="last_month"\s+checked', last)
    assert not re.search(r'value="all"\s+checked', last)
    # Чипы перезапрашивают тот же маршрут и подменяют корень панели.
    assert f'hx-get="/tutor/groups/{group_id}/payments"' in last
    assert 'hx-target="#group-payments-content"' in last


# --------------------------------------------------------------------------
# Пустая группа и изоляция
# --------------------------------------------------------------------------


def test_panel_empty_group_shows_zeros_and_hint(owner, client, group_factory):
    """Без участников — нули и пояснение вместо списка."""
    group_id = group_factory(tutor_id=owner)

    response = client.get(f"/tutor/groups/{group_id}/payments")

    assert response.status_code == 200
    assert "В группе пока нет учеников." in response.text
    assert money(0) in response.text
    assert "group-payments-member" not in response.text


def test_panel_no_lessons_count_label_for_zero_charges(
    owner,
    client,
    group_factory,
    group_member_factory,
    student_factory,
):
    """Участник без списаний: «Списано: 0 ₽» без подписи «0 занятий»."""
    group_id = group_factory(tutor_id=owner)
    student_id = student_factory(tutor_id=owner, first_name="Мария")
    group_member_factory(group_id=group_id, student_id=student_id)

    response = client.get(f"/tutor/groups/{group_id}/payments")

    assert f"Списано: {money(0)}" in response.text
    assert "0 занятий" not in response.text


@pytest.fixture()
def foreign_group(tutor_factory, student_factory, group_factory, group_member_factory):
    """Группа другого репетитора с участником и списанием."""
    foreign = tutor_factory(email="group-payments-foreign@example.com")
    group_id = group_factory(tutor_id=foreign, name="Чужая группа")
    student_id = student_factory(tutor_id=foreign, first_name="Чужойученик")
    group_member_factory(group_id=group_id, student_id=student_id)
    return group_id, student_id


def test_foreign_group_panel_is_not_found(owner, client, foreign_group):
    """Панель чужой группы — 404, данные не раскрываются."""
    group_id, _ = foreign_group

    response = client.get(f"/tutor/groups/{group_id}/payments")

    assert response.status_code == 404
    assert "Чужая группа" not in response.text
    assert "Чужойученик" not in response.text


def test_missing_group_panel_is_not_found(owner, client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/tutor/groups/{missing}/payments").status_code == 404


def test_group_panel_requires_login(client, foreign_group):
    """Без сессии — 303 на логин, как у всех маршрутов приложения."""
    group_id, _ = foreign_group

    response = client.get(f"/tutor/groups/{group_id}/payments", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
