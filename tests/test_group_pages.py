"""Страницы групп: список, карточки, партиал сетки и доступ (3.1–3.3)."""

import pytest

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="groups-owner-page@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "groups-owner-page@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


# --------------------------------------------------------------------------
# Доступ и страница (3.1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/tutor/groups"),
        ("get", "/tutor/groups/list"),
    ],
)
def test_group_pages_require_login(client, method, url):
    """Без сессии — редирект на вход, разметка групп не отдаётся."""
    response = getattr(client, method)(url, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_groups_page_renders_header_and_create_button(owner, client):
    response = client.get("/tutor/groups")
    assert response.status_code == 200
    assert "<h1>Группы</h1>" in response.text
    assert "Управление группами учеников" in response.text
    assert "Создать группу" in response.text
    # Активный пункт сайдбара — «Группы».
    assert 'nav-item nav-item--active' in response.text
    assert 'href="/tutor/groups"' in response.text


def test_groups_page_has_empty_state(owner, client):
    """Пустой список — пояснение, а не ошибка."""
    response = client.get("/tutor/groups")
    assert response.status_code == 200
    assert "Групп пока нет" in response.text
    assert "Создайте первую группу" in response.text


def test_groups_page_has_modal_container(owner, client):
    """Модалки создания и управления вставляются в `#modal`."""
    response = client.get("/tutor/groups")
    assert 'id="modal"' in response.text
    assert 'hx-get="/tutor/groups/new"' in response.text


# --------------------------------------------------------------------------
# Карточки групп (3.2)
# --------------------------------------------------------------------------


def test_card_shows_name_count_description_and_price(
    owner, client, group_factory, group_member_factory
):
    """Карточка: название, описание, «N / 10 учеников» и цена «1 200 ₽»."""
    group_id = group_factory(
        tutor_id=owner,
        name="Математика 9А",
        description="Подготовка к ОГЭ",
        price_per_lesson=1200,
    )
    group_member_factory(group_id=group_id)
    group_member_factory(group_id=group_id)

    response = client.get("/tutor/groups")
    assert response.status_code == 200
    assert "Математика 9А" in response.text
    assert "Подготовка к ОГЭ" in response.text
    assert "2 / 10 учеников" in response.text
    assert "1\u00a0200\u00a0₽" in response.text
    assert "Управление" in response.text


def test_card_without_description_and_price_hides_them(
    owner, client, group_factory
):
    """Без описания и цены карточка показывает название и счётчик."""
    group_factory(tutor_id=owner, name="Без описания")

    response = client.get("/tutor/groups")
    assert "Без описания" in response.text
    assert "0 / 10 учеников" in response.text
    # Блока цены нет вовсе — «0 ₽» не должно появляться.
    assert "₽" not in response.text
    assert "group-card__desc" not in response.text


def test_card_has_manage_button_and_menu(owner, client, group_factory):
    """Кнопка «Управление» и меню «...» с пунктами «Управление» и «Удалить»."""
    group_id = group_factory(tutor_id=owner, name="С меню")

    response = client.get("/tutor/groups")
    assert f'hx-get="/tutor/groups/{group_id}/edit"' in response.text
    assert 'aria-label="Действия с группой"' in response.text
    assert "group-card__menu" in response.text
    assert "Удалить" in response.text


def test_groups_page_shows_only_own_groups(owner, client, tutor_factory, group_factory):
    """Группы другого репетитора в списке не видны (изоляция)."""
    foreign = tutor_factory(email="groups-foreign-page@example.com")
    group_factory(tutor_id=owner, name="Своя группа")
    group_factory(tutor_id=foreign, name="Чужая группа")

    response = client.get("/tutor/groups")
    assert "Своя группа" in response.text
    assert "Чужая группа" not in response.text


# --------------------------------------------------------------------------
# Партиал сетки (3.3)
# --------------------------------------------------------------------------


def test_list_partial_returns_actual_cards(owner, client, group_factory):
    """Фрагмент для htmx содержит актуальные карточки и не содержит страницы."""
    group_factory(tutor_id=owner, name="Алгебра", price_per_lesson=900)

    response = client.get("/tutor/groups/list")
    assert response.status_code == 200
    assert "Алгебра" in response.text
    assert "900\u00a0₽" in response.text
    # Это партиал: ни сайдбара, ни <html>.
    assert 'class="sidebar"' not in response.text
    assert "<html" not in response.text


def test_list_partial_empty_state(owner, client):
    response = client.get("/tutor/groups/list")
    assert response.status_code == 200
    assert "Групп пока нет" in response.text


def test_list_partial_hides_foreign_groups(
    owner, client, tutor_factory, group_factory
):
    foreign = tutor_factory(email="groups-foreign-partial@example.com")
    group_factory(tutor_id=foreign, name="Чужая группа")

    response = client.get("/tutor/groups/list")
    assert "Чужая группа" not in response.text
    assert "Групп пока нет" in response.text
