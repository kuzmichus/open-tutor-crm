"""Тесты страницы «Брони и заявки»: разметка, история, изоляция, партиал.

Проверяется поведение через HTTP — теми же маршрутами, что у пользователя
(правило AGENTS.md): карточка ищется по тексту имени/интервала, действия —
по адресам форм, изоляция — отсутствием чужих данных в разметке.
"""

from datetime import UTC, datetime

import pytest

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="bookings-page@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "bookings-page@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def test_page_requires_login(client):
    """Без сессии страница редиректит на вход, а не отдаёт разметку."""
    response = client.get("/tutor/bookings", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/tutor/login")


def test_empty_page_shows_sections_and_share_link(client, owner):
    """Пустая страница: обе секции, пустые состояния и ссылка на запись."""
    response = client.get("/tutor/bookings")
    assert response.status_code == 200
    assert "Брони и заявки" in response.text
    assert "Ожидают подтверждения" in response.text
    assert "История" in response.text
    assert "Нет заявок, ожидающих подтверждения." in response.text
    assert "История пока пуста." in response.text
    # Пункт сайдбара подсвечен, ссылка ведёт на публичную страницу записи.
    assert "nav-item--active" in response.text
    assert f'href="/s/{owner}' in response.text
    assert "Поделиться расписанием" in response.text


def test_pending_booking_is_a_card_with_actions(
    client, owner, slot_factory, booking_factory
):
    """Ожидающая заявка — карточка с временем, данными и действиями."""
    slot_id = slot_factory(
        owner,
        starts_at=datetime(2027, 10, 26, 17, 15, tzinfo=UTC),
        duration_min=40,
    )
    booking_id = booking_factory(
        slot_id, name="John Dou", contact="+7 555 555-55-55"
    )

    response = client.get("/tutor/bookings")
    assert response.status_code == 200
    page = response.text
    # Данные заявки: имя, контакт, интервал и дата окна в зоне педагога.
    assert "John Dou" in page
    assert "+7 555 555-55-55" in page
    assert "17:15 – 17:55" in page
    assert "26 октября 2027" in page
    # «Принять» открывает диалог окна (там выбор ученика при совпадениях),
    # «Отклонить» — прямой POST.
    assert f'hx-get="/tutor/slots/{slot_id}"' in page
    assert f'hx-post="/tutor/bookings/{booking_id}/reject"' in page
    assert "Принять" in page
    assert "Отклонить" in page
    # Счётчик секции считает ожидающих.
    assert 'bookings-title__count">1<' in page


def test_history_row_shows_decision_and_date(
    client, owner, slot_factory, booking_factory
):
    """Завершённая бронь — строка истории с чипом статуса и датой решения."""
    slot_id = slot_factory(owner)
    booking_factory(
        slot_id,
        status="rejected",
        decided_at=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
    )

    response = client.get("/tutor/bookings")
    page = response.text
    assert "Отклонена" in page
    assert "15.10.2026" in page
    assert 'chip--rejected' in page
    # У завершённой брони действий нет.
    assert "Отменить" not in page


def test_confirmed_future_booking_is_cancellable(
    client, owner, slot_factory, booking_factory
):
    """Подтверждённая бронь на будущее — в истории с кнопкой «Отменить»."""
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id, status="confirmed")

    response = client.get("/tutor/bookings")
    page = response.text
    assert "Подтверждена" in page
    assert "Отменить" in page
    assert f'hx-post="/tutor/bookings/{booking_id}/cancel"' in page


def test_confirmed_past_booking_has_no_cancel(
    client, owner, slot_factory, booking_factory
):
    """Отменять прошедшее занятие поздно: кнопки у прошлой брони нет."""
    slot_id = slot_factory(
        owner, starts_at=datetime(2026, 1, 10, 10, 0, tzinfo=UTC)
    )
    booking_factory(
        slot_id,
        status="confirmed",
        decided_at=datetime(2026, 1, 9, 18, 0, tzinfo=UTC),
    )

    response = client.get("/tutor/bookings")
    assert "Отменить" not in response.text


def test_page_isolates_by_tutor(
    client, owner, tutor_factory, slot_factory, booking_factory
):
    """Чужие заявки на странице не видны: изоляция по репетитору окна."""
    other_id = tutor_factory(email="other-page@example.com")
    other_slot = slot_factory(other_id)
    booking_factory(other_slot, name="Чужая Заявка", contact="+7 111 111-11-11")

    response = client.get("/tutor/bookings")
    assert response.status_code == 200
    assert "Чужая Заявка" not in response.text
    assert "+7 111 111-11-11" not in response.text
    assert "Нет заявок, ожидающих подтверждения." in response.text


def test_list_partial_returns_fragment_only(
    client, owner, slot_factory, booking_factory
):
    """Партиал /list отдаёт список без сайдбара — для контейнера страницы."""
    slot_id = slot_factory(owner)
    booking_factory(slot_id, name="Мария Петрова")

    response = client.get("/tutor/bookings/list")
    assert response.status_code == 200
    assert "Мария Петрова" in response.text
    assert 'class="sidebar"' not in response.text
    assert "Брони и заявки" not in response.text


def test_page_loads_slot_dialog_script_before_alpine(client, owner):
    """Страница подключает slots.js до Alpine — диалог окна закрывается.

    «Принять» открывает диалог окна (`slot/_dialog.html`) в `#modal`: его
    закрытие (крестик, «Закрыть», Escape и подписка `slot-saved` после
    подтверждения) живёт в Alpine-компоненте `slotDialog`. Без скрипта
    компонент не зарегистрирован — диалог открывается, но не реагирует на
    закрытие. Скрипт идёт до alpine.min.js: подписка на `alpine:init`
    должна сработать раньше обхода DOM (правило AGENTS.md).
    """
    page = client.get("/tutor/bookings").text
    assert "/static/slots.js" in page
    assert page.index("/static/slots.js") < page.index("/static/alpine.min.js")


def test_sidebar_badge_container_is_rendered(client, owner):
    """Сайдбар несёт контейнер счётчика «Брони» с htmx-подгрузкой.

    Контейнер пустой: число подгружает партиал `/tutor/bookings/count` при
    загрузке страницы, перечитывает каждые 30 секунд (новая заявка с
    публичной страницы не шлёт событий у педагога) и по `slot-saved` —
    действия с бронью обновляют счётчик мгновенно (спека booking-management,
    «Счётчик необработанных заявок в сайдбаре»).
    """
    page = client.get("/tutor/bookings").text
    start = page.index('<aside class="sidebar"')
    sidebar = page[start : page.index("</aside>", start)]

    assert 'id="nav-badge-bookings"' in sidebar
    assert 'hx-get="/tutor/bookings/count"' in sidebar
    assert "every 30s" in sidebar
    assert "slot-saved from:body" in sidebar
    # Счётчик — часть сайдбара, а не страницы броней: виден отовсюду.
    home = client.get("/tutor/").text
    assert 'id="nav-badge-bookings"' in home


def test_sidebar_badge_has_css_rules(client, owner):
    """Кружок счётчика описан в CSS: виден с содержимым, скрыт пустым.

    Пустой контейнер обязан прятаться (`:empty`): кружок с нулём — не
    сигнал к действию, а в свёрнутом сайдбаре правило `.nav-item span`
    спрятало бы счётчик целиком без явного исключения.
    """
    from pathlib import Path

    styles = (
        Path(__file__).resolve().parent.parent
        / "app" / "static" / "styles.css"
    ).read_text(encoding="utf-8")

    assert ".nav-item__badge {" in styles
    assert ".nav-item__badge:empty { display: none; }" in styles
    assert ".nav-item .nav-item__badge:not(:empty)" in styles


def test_count_partial_shows_pending_count(
    client, owner, slot_factory, booking_factory
):
    """Партиал отдаёт число ожидающих: подтверждённая и завершённая — не в счёт.

    Окна на разное время: у `slots` UNIQUE на (tutor_id, starts_at).
    """
    booking_factory(
        slot_factory(owner, starts_at=datetime(2027, 10, 26, 10, 0, tzinfo=UTC))
    )
    booking_factory(
        slot_factory(owner, starts_at=datetime(2027, 10, 26, 11, 0, tzinfo=UTC))
    )
    booking_factory(
        slot_factory(owner, starts_at=datetime(2027, 10, 26, 12, 0, tzinfo=UTC)),
        status="confirmed",
    )
    booking_factory(
        slot_factory(owner, starts_at=datetime(2027, 10, 26, 13, 0, tzinfo=UTC)),
        status="rejected",
    )

    response = client.get("/tutor/bookings/count")
    assert response.status_code == 200
    assert response.text == "2"


def test_count_partial_is_empty_without_pending(client, owner):
    """Без ожидающих заявок — пустое тело: контейнер остаётся без кружка."""
    response = client.get("/tutor/bookings/count")
    assert response.status_code == 200
    assert response.text == ""


def test_count_partial_isolates_by_tutor(
    client, owner, tutor_factory, slot_factory, booking_factory
):
    """Чужие заявки в счётчик не попадают: владелец брони — через окно."""
    booking_factory(
        slot_factory(owner, starts_at=datetime(2027, 10, 26, 10, 0, tzinfo=UTC))
    )
    other_id = tutor_factory(email="count-other@example.com")
    booking_factory(
        slot_factory(other_id, starts_at=datetime(2027, 10, 26, 10, 0, tzinfo=UTC))
    )
    booking_factory(
        slot_factory(other_id, starts_at=datetime(2027, 10, 26, 11, 0, tzinfo=UTC))
    )

    assert client.get("/tutor/bookings/count").text == "1"


def test_count_partial_requires_login(client):
    """Без сессии партиал редиректит на вход, а не отдаёт число."""
    response = client.get("/tutor/bookings/count", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/tutor/login")


def test_count_partial_updates_after_confirm_and_reject(
    client, owner, slot_factory, booking_factory
):
    """После подтверждения и отклонения партиал отдаёт уменьшенное число.

    Окна на разное время: подтверждение проверяет пересечение с другими
    окнами (`slot/services/busy.py`), два окна в одно время сделали бы
    подтверждение невозможным.
    """
    first = booking_factory(
        slot_factory(owner, starts_at=datetime(2027, 10, 26, 10, 0, tzinfo=UTC))
    )
    second = booking_factory(
        slot_factory(owner, starts_at=datetime(2027, 10, 26, 12, 0, tzinfo=UTC))
    )

    assert client.get("/tutor/bookings/count").text == "2"

    client.post(
        f"/tutor/bookings/{first}/confirm",
        data={"kind": "adult"},
        headers={"HX-Request": "true"},
    )
    assert client.get("/tutor/bookings/count").text == "1"

    client.post(
        f"/tutor/bookings/{second}/reject",
        headers={"HX-Request": "true"},
    )
    assert client.get("/tutor/bookings/count").text == ""
