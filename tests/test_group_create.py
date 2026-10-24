"""Создание группы и ученика из мини-формы (4.1–4.6)."""

import html
import json
import re

import pytest

from app.database import SessionLocal
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.group.services.members import MAX_MEMBERS
from app.student.models.student import Student

PASSWORD = "Секретный-Пароль-1"


def _attr_json(markup: str, name: str) -> object:
    """JSON из `data-`атрибута (в разных шаблонах кавычки разные)."""
    match = re.search(rf"""{name}=(?:'([^']*)'|"([^"]*)")""", markup)
    assert match, f"нет атрибута {name} в ответе"
    raw = match.group(1) if match.group(1) is not None else match.group(2)
    return json.loads(html.unescape(raw))


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="groups-create@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "groups-create@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


# --------------------------------------------------------------------------
# Модалка «Новая группа» (4.1)
# --------------------------------------------------------------------------


def test_new_group_modal_has_required_fields(owner, client):
    response = client.get("/tutor/groups/new")
    assert response.status_code == 200
    assert "Новая группа" in response.text
    assert (
        "Создайте группу для нескольких учеников. "
        "Вы сможете назначать уроки сразу всей группе." in response.text
    )
    assert "Название группы *" in response.text
    assert "Цена за урок (с чел.)" in response.text
    assert "Описание" in response.text
    assert "Отмена" in response.text
    assert "Сохранить" in response.text


def test_new_group_modal_shows_member_block(owner, client):
    """Блок учеников: подпись лимита и пустой состав."""
    response = client.get("/tutor/groups/new")
    assert f"Макс: {MAX_MEMBERS}" in response.text
    assert "Нет добавленных учеников" in response.text
    assert 'name="members_form" value="1"' in response.text


def test_new_group_modal_has_no_teacher_subject_or_rate(owner, client):
    """Полей «Педагог», «Предмет», «Ставка педагога» в форме нет."""
    response = client.get("/tutor/groups/new")
    for forbidden in ("Педагог", "Предмет", "Ставка педагога"):
        assert forbidden not in response.text


# --------------------------------------------------------------------------
# Выбор учеников и мини-форма (4.2, 4.4, 4.6)
# --------------------------------------------------------------------------


def test_new_group_modal_mounts_group_form_component(owner, client):
    """Точка монтирования Alpine и подключённый ассет страницы групп."""
    modal = client.get("/tutor/groups/new").text
    assert 'x-data="groupForm()"' in modal
    assert "data-options=" in modal
    assert 'data-max-members="10"' in modal
    assert "Добавить ученика..." in modal

    page = client.get("/tutor/groups").text
    assert "/static/groups.js" in page
    # Ассет идёт до Alpine: `alpine:init` подписывается раньше обхода DOM.
    assert page.index("groups.js") < page.index("alpine.min.js")


def test_member_created_event_reaches_window_listener():
    """Событие создания участника всплывает до `window`.

    Регрессия из браузерного прогона: `document.dispatchEvent` без
    `bubbles: true` не доходит до слушателя Alpine
    (`@group-member-created.window`), и строка состава не появлялась.
    """
    from pathlib import Path

    js = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "groups.js"
    ).read_text(encoding="utf-8")

    assert "group-member-created" in js
    assert "bubbles: true" in js
    # Модалки слушают событие на window — иначе строка не добавится.
    for template in ("group/_new_group.html", "group/_manage.html"):
        html = (
            Path(__file__).resolve().parent.parent
            / "app"
            / "group"
            / "templates"
            / template
        ).read_text(encoding="utf-8")
        assert '@group-member-created.window="applyMemberUpdate($event.detail)"' in html


def test_add_student_item_is_after_divider(owner, client):
    """В конце списка выбора — разделитель и пункт «Добавить ученика»."""
    html = client.get("/tutor/groups/new").text
    divider = html.index("combobox__divider")
    item = html.index("combobox__option--action")
    assert divider < item
    assert "Добавить ученика" in html[item:]


def test_mini_form_is_a_div_without_nested_form(owner, client):
    """Мини-форма — `div` с полями, вложенного `<form>` нет (решение D9)."""
    html = client.get("/tutor/groups/new").text
    assert html.count("<form") == 1  # только форма самой модалки
    assert 'class="group-mini"' in html
    mini = html[html.index('class="group-mini"') : html.index("group-members-update")]
    for label in ("Имя *", "Фамилия", "Телефон"):
        assert label in mini
    assert "Создать" in mini
    assert "Отменить" in mini
    # Поля выбора группы в мини-форме нет: группа берётся из контекста.
    assert "group_id" not in mini


# --------------------------------------------------------------------------
# Создание группы (4.3)
# --------------------------------------------------------------------------


def test_create_group_with_members(owner, client, student_factory):
    """Создание группы с участниками; сетка перезапрашивается событием."""
    first = student_factory(tutor_id=owner, first_name="Мария")
    second = student_factory(tutor_id=owner, first_name="Иван")

    response = client.post(
        "/tutor/groups",
        data={
            "name": "Математика 9А",
            "price": "1200",
            "description": "Подготовка к ОГЭ",
            "members_form": "1",
            "members": [first, second],
            f"member_joined_{first}": "2026-09-01",
            f"member_price_{second}": "1000",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "group-saved"

    with SessionLocal() as db:
        group = db.query(Group).filter_by(tutor_id=owner).one()
        assert group.name == "Математика 9А"
        assert group.price_per_lesson == 1200
        assert group.description == "Подготовка к ОГЭ"
        members = {
            member.student_id: member
            for member in db.query(GroupMember).filter_by(group_id=group.id)
        }
    assert set(members) == {first, second}
    assert members[first].joined_at.strftime("%Y-%m-%d") == "2026-09-01"
    assert members[second].price_override == 1000

    page = client.get("/tutor/groups").text
    assert "Математика 9А" in page
    assert "2 / 10 учеников" in page


def test_create_group_without_members(owner, client):
    """Группу можно создать без участников."""
    response = client.post(
        "/tutor/groups",
        data={"name": "Пустая", "members_form": "1"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    with SessionLocal() as db:
        group = db.query(Group).filter_by(tutor_id=owner).one()
        assert group.name == "Пустая"
        assert db.query(GroupMember).filter_by(group_id=group.id).count() == 0


def test_create_group_empty_name_shows_error(owner, client):
    """Пустое название — группа не создаётся, ошибка в модалке."""
    response = client.post(
        "/tutor/groups",
        data={"name": "   ", "members_form": "1"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Укажите название группы." in response.text
    # Модалка отрисована повторно, а не закрыта.
    assert "Новая группа" in response.text
    with SessionLocal() as db:
        assert db.query(Group).filter_by(tutor_id=owner).count() == 0


def test_create_group_over_limit_shows_error(owner, client, student_factory):
    """Больше 10 участников — группа не создаётся."""
    ids = [student_factory(tutor_id=owner) for _ in range(MAX_MEMBERS + 1)]
    response = client.post(
        "/tutor/groups",
        data={"name": "Слишком большая", "members_form": "1", "members": ids},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert f"В группе может быть не более {MAX_MEMBERS} участников." in response.text
    with SessionLocal() as db:
        assert db.query(Group).filter_by(tutor_id=owner).count() == 0


def test_create_group_error_keeps_submitted_members(owner, client, student_factory):
    """При ошибке состав из формы не теряется."""
    student_id = student_factory(tutor_id=owner, first_name="Сохранименя")
    response = client.post(
        "/tutor/groups",
        data={"name": "", "members_form": "1", "members": [student_id]},
        headers={"HX-Request": "true"},
    )
    rows = _attr_json(response.text, "data-members")
    assert [row["id"] for row in rows] == [student_id]
    assert rows[0]["name"] == "Сохранименя"
    # Уже добавленный участник не предлагается повторно.
    options = _attr_json(response.text, "data-options")
    assert student_id not in [option["id"] for option in options]


def test_create_group_without_htmx_redirects(owner, client):
    """Обычная отправка формы ведёт на список групп."""
    response = client.post(
        "/tutor/groups",
        data={"name": "Без htmx", "members_form": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/groups"


# --------------------------------------------------------------------------
# Создание ученика из мини-формы (4.5)
# --------------------------------------------------------------------------


def test_mini_form_creates_student_and_returns_member_row(owner, client):
    """Ученик создаётся и возвращается строкой состава с датой «сегодня»."""
    response = client.post(
        "/tutor/groups/students",
        data={"first_name": "Пётр", "last_name": "Сидоров", "phone": "8 916 123-45-67"},
    )
    assert response.status_code == 200
    assert 'id="group-members-update"' in response.text
    member = _attr_json(response.text, "data-member")
    assert member["name"] == "Пётр Сидоров"
    assert "data-error" not in response.text

    with SessionLocal() as db:
        student = db.query(Student).filter_by(tutor_id=owner).one()
        assert student.first_name == "Пётр"
        assert student.last_name == "Сидоров"
        # Статус и тип по умолчанию (D9).
        assert student.status == "new"
        assert student.kind == "child"
        # Телефон нормализован тем же правилом, что и в карточке ученика.
        assert student.phone == "+7 916 123-45-67"
        student_id = student.id

    # Дата вступления — «сегодня» в зоне педагога (design D7 задачи
    # store-datetimes-in-utc), а не дата машины: фикстура задаёт зону UTC,
    # поэтому ожидание строится на UTC-моменте, а не на `date.today()`.
    from app.tutor.services.clock import utcnow

    assert member["id"] == student_id
    assert member["joined"] == utcnow().date().isoformat()
    assert member["price"] == ""


def test_mini_form_empty_name_is_rejected(owner, client):
    """Пустое имя — ученик не создаётся, ошибка в ответе."""
    response = client.post(
        "/tutor/groups/students",
        data={"first_name": "  ", "last_name": "Без Имени"},
    )
    assert response.status_code == 200
    assert 'data-error="Укажите имя ученика."' in response.text
    with SessionLocal() as db:
        assert db.query(Student).filter_by(tutor_id=owner).count() == 0


def test_mini_form_invalid_phone_is_rejected(owner, client):
    """Невалидный телефон — ошибка, ученик не создаётся."""
    response = client.post(
        "/tutor/groups/students",
        data={"first_name": "Пётр", "phone": "позвонить маме"},
    )
    assert response.status_code == 200
    assert 'data-error="Укажите корректный телефон."' in response.text
    with SessionLocal() as db:
        assert db.query(Student).filter_by(tutor_id=owner).count() == 0


def test_mini_form_excludes_new_student_from_options(owner, client, student_factory):
    """Созданный ученик не предлагается в списке выбора — он уже в составе."""
    student_factory(tutor_id=owner, first_name="Существующий")
    response = client.post("/tutor/groups/students", data={"first_name": "Новый"})

    member = _attr_json(response.text, "data-member")
    options = _attr_json(response.text, "data-options")

    assert member["name"] == "Новый"
    names = [option["name"] for option in options]
    assert "Существующий" in names
    # Созданный ученик уже в составе формы, в списке выбора его нет.
    assert "Новый" not in names


def test_mini_form_creates_student_for_current_tutor_only(owner, client, tutor_factory):
    """Ученик создаётся у вошедшего репетитора, чужой id из формы игнорируется."""
    foreign = tutor_factory(email="groups-mini-foreign@example.com")
    response = client.post(
        "/tutor/groups/students",
        data={"first_name": "Свой", "tutor_id": foreign},
    )
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.query(Student).filter_by(tutor_id=owner).count() == 1
        assert db.query(Student).filter_by(tutor_id=foreign).count() == 0


@pytest.mark.parametrize("url", ["/tutor/groups/new", "/tutor/groups/students"])
def test_create_endpoints_require_login(client, url):
    """Без сессии модалка и мини-форма не отдаются."""
    method = client.get if url.endswith("/new") else client.post
    response = method(url, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
