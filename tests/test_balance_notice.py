"""Плашка «сегодня занятие, а на счёте не хватает денег» (TOCRM-65).

Поведение проверяется через HTTP тем же путём, что у пользователя: контейнер
на страницах кабинета запрашивает партиал `/tutor/notices/balance`, разметка
ищется по тексту и атрибутам. «Сегодня» — дата в зоне педагога (фабрика даёт
зону UTC), поэтому уроки строятся от `utcnow()`.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest

from app.tutor.services.clock import utcnow

PASSWORD = "Секретный-Пароль-1"

# Неразрывные пробелы в суммах — формат `money()` модуля финансов.
NBSP = "\u00a0"


def _login(client, tutor_factory, email: str, name: str = "Репетитор") -> str:
    """Создаёт репетитора и входит под ним; возвращает id."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _key_of(html: str) -> str:
    """Ключ клиентского закрытия плашки (Alpine `noticeBanner`)."""
    match = re.search(r"noticeBanner\('([^']*)'\)", html)
    assert match, "в плашке нет ключа закрытия"
    return match.group(1)


def _today() -> str:
    """Сегодняшняя дата педагога в ISO-формате (фабрика даёт зону UTC)."""
    return utcnow().date().isoformat()


def test_requires_session(client):
    """Без сессии партиал недоступен: редирект на вход."""
    response = client.get("/tutor/notices/balance", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_shows_single_student_shortfall(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """Баланс 500 при цене 2 000 — плашка с суммой нехватки и ссылкой."""
    tutor_id = _login(client, tutor_factory, "balance-one@example.com")
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван")
    operation_factory(student_id=student_id, kind="payment", amount=500)
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow(),
        price=2000,
    )

    response = client.get("/tutor/notices/balance")
    assert response.status_code == 200
    html = response.text
    assert (
        f"Сегодня занятие у 1 ученика, а на счёте не хватает 1{NBSP}500{NBSP}₽"
        in html
    )
    # «Открыть» ведёт в список учеников, которым не хватает на сегодня
    # (design D4): фильтр должников скрыл бы ученика с балансом 500 ₽.
    assert 'href="/tutor/students?shortfall=1"' in html
    assert 'aria-label="Скрыть напоминание"' in html
    # Ключ закрытия — состав учеников и сумма нехватки.
    assert _key_of(html) == f"debt:{_today()}:{student_id}#1500"


def test_red_banner_markup(
    client, tutor_factory, student_factory, lesson_factory
):
    """Плашка опасного тона: модификатор класса и иконка кошелька."""
    tutor_id = _login(client, tutor_factory, "balance-markup@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=utcnow(), price=1200)

    html = client.get("/tutor/notices/balance").text
    assert "notice-banner--danger" in html
    assert 'data-lucide="wallet"' in html


@pytest.mark.parametrize(
    "lesson",
    [
        pytest.param(
            {"status": "planned", "starts_at": utcnow() + timedelta(days=1)},
            id="tomorrow",
        ),
        pytest.param(
            {"status": "planned", "starts_at": utcnow() - timedelta(days=1)},
            id="yesterday",
        ),
        pytest.param({"status": "completed", "starts_at": utcnow()}, id="completed"),
        pytest.param({"status": "cancelled", "starts_at": utcnow()}, id="cancelled"),
        pytest.param(
            {"status": "rescheduled", "starts_at": utcnow()}, id="rescheduled"
        ),
        pytest.param(
            {"status": "planned", "starts_at": utcnow(), "price": None},
            id="no-price",
        ),
    ],
)
def test_nothing_to_show(
    lesson, client, tutor_factory, student_factory, lesson_factory
):
    """Не сегодняшний, не «Запланирован» или без цены — плашки нет."""
    tutor_id = _login(client, tutor_factory, f"balance-none-{lesson['status']}@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, **lesson)

    response = client.get("/tutor/notices/balance")

    assert response.status_code == 200
    assert response.text == ""


def test_enough_money_no_banner(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """Денег хватает — пустое тело, а не «всё оплачено»."""
    tutor_id = _login(client, tutor_factory, "balance-enough@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    operation_factory(student_id=student_id, kind="payment", amount=5000)
    lesson_factory(student_id=student_id, status="planned", starts_at=utcnow(), price=1200)

    assert client.get("/tutor/notices/balance").text == ""


def test_two_students_count_and_total(
    client, tutor_factory, student_factory, lesson_factory
):
    """Два ученика без денег: «2 учеников» и сумма обеих нехваток."""
    tutor_id = _login(client, tutor_factory, "balance-two@example.com")
    first = student_factory(tutor_id=tutor_id, first_name="Первый")
    second = student_factory(tutor_id=tutor_id, first_name="Второй")
    lesson_factory(student_id=first, status="planned", starts_at=utcnow(), price=2000)
    lesson_factory(student_id=second, status="planned", starts_at=utcnow(), price=1500)

    html = client.get("/tutor/notices/balance").text
    assert (
        f"Сегодня занятия у 2 учеников, а на счёте не хватает 3{NBSP}500{NBSP}₽"
        in html
    )
    assert _key_of(html) == f"debt:{_today()}:{'|'.join(sorted((first, second)))}#3500"


def test_same_student_twice_counted_once(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """Два урока одного ученика: один ученик, нехватка — по сумме цен дня."""
    tutor_id = _login(client, tutor_factory, "balance-twice@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    operation_factory(student_id=student_id, kind="payment", amount=500)
    # Полдень сегодняшнего дня: второй урок (+1 час) остаётся в тех же
    # сутках независимо от времени прогона теста.
    noon = utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    lesson_factory(student_id=student_id, status="planned", starts_at=noon, price=2000)
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=noon + timedelta(hours=1),
        price=1000,
    )

    html = client.get("/tutor/notices/balance").text
    assert (
        f"Сегодня занятие у 1 ученика, а на счёте не хватает 2{NBSP}500{NBSP}₽"
        in html
    )
    assert _key_of(html) == f"debt:{_today()}:{student_id}#2500"


def test_group_lesson_counts_each_participant(
    client,
    tutor_factory,
    student_factory,
    group_factory,
    group_member_factory,
    lesson_factory,
    operation_factory,
):
    """Групповой урок: цена участника своя, оплативший не считается."""
    tutor_id = _login(client, tutor_factory, "balance-group@example.com")
    group_id = group_factory(tutor_id=tutor_id, name="Математика 7Б", price_per_lesson=1000)
    poor = student_factory(tutor_id=tutor_id, first_name="Бедный")
    rich = student_factory(tutor_id=tutor_id, first_name="Богатый")
    group_member_factory(group_id=group_id, student_id=poor)
    group_member_factory(group_id=group_id, student_id=rich, price_override=1500)
    operation_factory(student_id=rich, kind="payment", amount=5000)
    lesson_factory(
        student_id=None,
        group_id=group_id,
        status="planned",
        starts_at=utcnow(),
        price=None,
    )

    html = client.get("/tutor/notices/balance").text
    assert (
        f"Сегодня занятие у 1 ученика, а на счёте не хватает 1{NBSP}000{NBSP}₽"
        in html
    )
    assert _key_of(html) == f"debt:{_today()}:{poor}#1000"


def test_isolation(client, tutor_factory, student_factory, lesson_factory):
    """Уроки и ученики чужого репетитора в плашку не попадают."""
    other_tutor = tutor_factory(email="balance-other@example.com")
    other_student = student_factory(tutor_id=other_tutor, first_name="Чужой")
    lesson_factory(
        student_id=other_student, status="planned", starts_at=utcnow(), price=2000
    )

    _login(client, tutor_factory, "balance-mine@example.com")
    assert client.get("/tutor/notices/balance").text == ""


def test_dismiss_key_follows_amount_and_composition(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """Ключ закрытия: пока состав и сумма те же — плашка остаётся закрытой.

    Частичная оплата меняет сумму — ключ другой, и напоминание
    возвращается. Полная оплата убирает плашку вовсе (сервер не рендерит
    разметку), поэтому потерять долг молча нельзя.
    """
    tutor_id = _login(client, tutor_factory, "balance-key@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=utcnow(), price=2000)

    one = _key_of(client.get("/tutor/notices/balance").text)
    # Тот же состав и та же сумма — тот же ключ: повторный опрос htmx
    # не «оживляет» закрытую плашку.
    assert _key_of(client.get("/tutor/notices/balance").text) == one

    operation_factory(student_id=student_id, kind="payment", amount=500)
    partial = _key_of(client.get("/tutor/notices/balance").text)
    assert partial != one
    assert partial.endswith("#1500")

    operation_factory(student_id=student_id, kind="payment", amount=2000)
    assert "noticeBanner(" not in client.get("/tutor/notices/balance").text


def test_dismiss_key_follows_local_day(
    client, tutor_factory, student_factory, lesson_factory, monkeypatch
):
    """Ключ закрытия содержит день педагога: завтрашний долг не скрывается.

    Закрытие хранится в localStorage бессрочно, поэтому без даты в ключе
    закрытое сегодня напоминание с тем же составом и суммой молча скрыло бы
    такое же напоминание следующего дня — а регулярное расписание даёт
    ровно такой повтор (замечание ревью №2).
    """
    tutor_id = _login(client, tutor_factory, "balance-key-day@example.com")
    student_id = student_factory(tutor_id=tutor_id)

    def at(moment: datetime) -> None:
        """Фиксирует «сейчас» для расчёта дня педагога."""
        monkeypatch.setattr("app.common.services.tutor_time.utcnow", lambda: moment)

    first_day = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    at(first_day)
    lesson_factory(
        student_id=student_id, status="planned", starts_at=first_day, price=1500
    )
    today_key = _key_of(client.get("/tutor/notices/balance").text)
    assert today_key == f"debt:2026-11-10:{student_id}#1500"
    # Внутри одного дня ключ стабилен: повторный опрос htmx не «оживляет»
    # закрытую плашку.
    assert _key_of(client.get("/tutor/notices/balance").text) == today_key

    next_day = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    at(next_day)
    lesson_factory(
        student_id=student_id, status="planned", starts_at=next_day, price=1500
    )
    tomorrow_key = _key_of(client.get("/tutor/notices/balance").text)
    assert tomorrow_key == f"debt:2026-11-11:{student_id}#1500"
    assert tomorrow_key != today_key


def test_container_on_cabinet_pages(client, tutor_factory, student_factory):
    """Контейнер плашки есть на страницах кабинета и запрашивает партиал."""
    tutor_id = _login(client, tutor_factory, "balance-pages@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    for url in (
        "/tutor/",
        "/tutor/students",
        "/tutor/lessons",
        "/tutor/calendar",
        "/tutor/groups",
        "/tutor/finance",
        "/tutor/profile",
        f"/tutor/students/{student_id}",
    ):
        html = client.get(url).text
        assert 'id="tutor-balance-notice"' in html, url
        assert 'hx-get="/tutor/notices/balance"' in html, url


# --------------------------------------------------------------------------
# Адресат ссылки «Открыть»: список учеников с нехваткой на сегодня
# --------------------------------------------------------------------------


def test_open_link_filter_shows_positive_balance_shortfall(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """Баланс 500 ₽ при цене 2 000 ₽ — не долг, но в фильтре «Открыть» виден.

    Фильтр должников (`debtors=1`) оставляет только отрицательный баланс и
    такого ученика скрыл бы: плашка сообщала бы нехватку, а список был бы
    пуст. Поэтому ссылка ведёт в собственный фильтр нехватки.
    """
    tutor_id = _login(client, tutor_factory, "balance-filter@example.com")
    poor = student_factory(tutor_id=tutor_id, first_name="Недоплативший")
    operation_factory(student_id=poor, kind="payment", amount=500)
    lesson_factory(student_id=poor, status="planned", starts_at=utcnow(), price=2000)

    page = client.get("/tutor/students", params={"shortfall": "1"}).text
    assert "Недоплативший" in page
    # Плашка фильтра объясняет, почему список неполный, и даёт выход.
    assert "не хватает денег на сегодняшние занятия" in page
    assert 'href="/tutor/students"' in page
    # Скрытое поле сохраняет фильтр при поиске и сортировке в партиале.
    assert 'name="shortfall" value="1"' in page


def test_open_link_filter_skips_paid_and_unrelated_students(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """В фильтре нехватки нет тех, кому хватает, и тех, у кого нет уроков."""
    tutor_id = _login(client, tutor_factory, "balance-filter-skip@example.com")
    payer = student_factory(tutor_id=tutor_id, first_name="Оплативший")
    operation_factory(student_id=payer, kind="payment", amount=5000)
    lesson_factory(student_id=payer, status="planned", starts_at=utcnow(), price=2000)
    idle = student_factory(tutor_id=tutor_id, first_name="БезУрока")

    page = client.get("/tutor/students", params={"shortfall": "1"}).text
    assert "Оплативший" not in page
    assert "БезУрока" not in page
    # Пустая выборка — заглушка, а не весь список.
    assert "Ничего не найдено" in page


def test_open_link_filter_isolated_by_tutor(
    client, tutor_factory, student_factory, lesson_factory
):
    """Чужие ученики в фильтр нехватки не попадают."""
    other_tutor = tutor_factory(email="balance-filter-other@example.com")
    other_student = student_factory(tutor_id=other_tutor, first_name="ЧужойДолжник")
    lesson_factory(
        student_id=other_student, status="planned", starts_at=utcnow(), price=2000
    )

    _login(client, tutor_factory, "balance-filter-mine@example.com")
    page = client.get("/tutor/students", params={"shortfall": "1"}).text
    assert "ЧужойДолжник" not in page
    assert "Ничего не найдено" in page


def test_open_link_filter_survives_list_partial(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """Партиал списка (поиск, смена вида) тоже уважает фильтр нехватки."""
    tutor_id = _login(client, tutor_factory, "balance-filter-partial@example.com")
    poor = student_factory(tutor_id=tutor_id, first_name="Недоплативший")
    operation_factory(student_id=poor, kind="payment", amount=500)
    lesson_factory(student_id=poor, status="planned", starts_at=utcnow(), price=2000)
    student_factory(tutor_id=tutor_id, first_name="Обычный")

    page = client.get("/tutor/students/list", params={"shortfall": "1"}).text
    assert "Недоплативший" in page
    assert "Обычный" not in page

