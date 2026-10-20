"""Управление группой: модалка, вкладки, настройки, заметки, изоляция (5.1–5.7)."""

import html
import json
import re
from datetime import UTC, datetime

import pytest

from app.database import SessionLocal
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.student.models.student import Student

PASSWORD = "Секретный-Пароль-1"


def _attr_json(markup: str, name: str) -> object:
    """JSON из `data-`атрибута (Jinja экранирует кириллицу)."""
    match = re.search(rf"""{name}=(?:'([^']*)'|"([^"]*)")""", markup)
    assert match, f"нет атрибута {name} в ответе"
    raw = match.group(1) if match.group(1) is not None else match.group(2)
    return json.loads(html.unescape(raw))


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="groups-manage@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "groups-manage@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _group_with_member(owner, student_factory, **group_extra):
    """Группа с одним участником, вступившим 14.10.2026."""
    student_id = student_factory(tutor_id=owner, first_name="Мария", last_name="Петрова")
    with SessionLocal() as db:
        group = Group(tutor_id=owner, name=group_extra.pop("name", "A"), **group_extra)
        db.add(group)
        db.flush()
        db.add(
            GroupMember(
                group_id=group.id,
                student_id=student_id,
                joined_at=datetime(2026, 10, 14, tzinfo=UTC),
            )
        )
        db.commit()
        return group.id, student_id


# --------------------------------------------------------------------------
# Модалка управления (5.1)
# --------------------------------------------------------------------------


def test_manage_modal_structure(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)

    response = client.get(f"/tutor/groups/{group_id}/edit")
    assert response.status_code == 200
    assert "Группа A" in response.text
    assert "Группа · участников: 1" in response.text
    # Пять вкладок, «Общее» активна по умолчанию.
    for label in ("Общее", "Расписание", "Занятия", "Оплаты", "Настройки"):
        assert label in response.text
    assert "tab--active" in response.text
    # Футер модалки.
    assert "Удалить" in response.text
    assert "Отмена" in response.text
    assert "Сохранить" in response.text


def test_manage_modal_has_five_tabs(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text

    assert html.count('role="tab"') == 5
    assert 'role="tablist"' in html
    for panel in ("general", "schedule", "lessons", "payments", "settings"):
        assert f'data-tab-panel="{panel}"' in html


def test_manage_modal_opens_on_general_tab(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text
    assert "groupManage('general')" in html


# --------------------------------------------------------------------------
# Вкладка «Общее» (5.2)
# --------------------------------------------------------------------------


def test_general_tab_shows_summary(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text

    assert "Участники" in html
    assert "1 из 10" in html
    assert "Расписание" in html
    assert "Ближайшее занятие" in html
    # Заглушки сводки: прочерки, а не выдуманные данные.
    assert html.count("—") >= 2


def test_general_tab_has_meeting_url_field(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text

    assert "Постоянная ссылка на встречу" in html
    assert 'name="meeting_url"' in html
    # Пояснение к полю.
    assert "Одна ссылка на все занятия группы" in html


def test_general_tab_shows_roster_with_join_dates(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text

    assert "Состав (1)" in html
    assert "Мария Петрова" in html
    assert "в группе с 14.10.2026" in html


def test_general_tab_upcoming_lessons_is_stub(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text

    assert "Ближайшие занятия" in html
    assert "Занятия группы появятся здесь позже." in html


def test_general_tab_has_notes_with_explanation(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text

    assert "Заметки к группе" in html
    assert "Ученики заметки не видят." in html
    assert 'name="notes"' in html


def test_general_tab_shows_empty_roster(owner, client, group_factory):
    group_id = group_factory(tutor_id=owner, name="Пустая")
    html = client.get(f"/tutor/groups/{group_id}/edit").text
    assert "Состав (0)" in html
    assert "В группе пока нет учеников." in html


# --------------------------------------------------------------------------
# Заглушки вкладок (5.3)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("panel", "text"),
    [
        ("schedule", "Расписание группы появится позже."),
        ("lessons", "Занятия группы появятся позже."),
        ("payments", "Оплаты группы появятся позже."),
    ],
)
def test_stub_tabs_explain_and_have_no_dead_actions(
    owner, client, student_factory, panel, text
):
    """Каждая заглушка поясняет и не ведёт в несуществующие маршруты."""
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text

    assert text in html
    start = html.index(f'data-tab-panel="{panel}"')
    end = html.index('data-tab-panel="', start + 1)
    section = html[start:end]
    # В заглушке нет кнопок и ссылок — только пояснение.
    assert "<button" not in section
    assert "<a " not in section


# --------------------------------------------------------------------------
# Вкладка «Настройки» (5.4)
# --------------------------------------------------------------------------


def test_settings_tab_prefills_group_data(owner, client, student_factory):
    group_id, _ = _group_with_member(
        owner,
        student_factory,
        name="Химия",
        price_per_lesson=1200,
        description="9 класс",
    )
    html = client.get(f"/tutor/groups/{group_id}/edit").text

    assert "Название группы *" in html
    assert 'value="Химия"' in html
    assert "Цена за урок (с чел.)" in html
    assert 'value="1200"' in html
    assert "9 класс" in html


def test_settings_tab_prefills_member_date_and_price(owner, client, student_factory):
    group_id, student_id = _group_with_member(owner, student_factory)
    with SessionLocal() as db:
        member = db.query(GroupMember).filter_by(group_id=group_id).one()
        member.price_override = 1000
        db.commit()

    html = client.get(f"/tutor/groups/{group_id}/edit").text
    # Имена полей строятся Alpine из id участника (D4).
    assert "member_joined_" in html
    assert "member_price_" in html

    rows = _attr_json(html, "data-members")
    assert [row["id"] for row in rows] == [student_id]
    assert rows[0]["joined"] == "2026-10-14"
    assert rows[0]["price"] == "1000"


def test_settings_tab_has_add_student_item(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text
    assert "Добавить ученика" in html
    assert "Макс: 10" in html


def test_settings_tab_excludes_existing_members_from_options(
    owner, client, student_factory
):
    """Уже состоящие в группе не предлагаются в списке выбора."""
    group_id, student_id = _group_with_member(owner, student_factory)
    student_factory(tutor_id=owner, first_name="Свободный")

    html = client.get(f"/tutor/groups/{group_id}/edit").text
    assert "Свободный" in html
    # Мария уже в группе — в опциях выбора её нет.
    options = _attr_json(html, "data-options")
    assert student_id not in [option["id"] for option in options]
    assert "Свободный" in [option["name"] for option in options]


def test_settings_tab_has_no_teacher_subject_or_rate(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    html = client.get(f"/tutor/groups/{group_id}/edit").text
    for forbidden in ("Педагог", "Предмет", "Ставка педагога"):
        assert forbidden not in html


# --------------------------------------------------------------------------
# Сохранение изменений (5.5)
# --------------------------------------------------------------------------


def test_update_renames_group_and_price(owner, client, student_factory):
    group_id, student_id = _group_with_member(owner, student_factory, name="Старое")

    response = client.post(
        f"/tutor/groups/{group_id}",
        data={
            "name": "Новое имя",
            "price": "1500",
            "description": "Описание",
            "members_form": "1",
            "members": [student_id],
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "group-saved"

    with SessionLocal() as db:
        group = db.get(Group, group_id)
        assert group.name == "Новое имя"
        assert group.price_per_lesson == 1500
        assert group.description == "Описание"

    page = client.get("/tutor/groups").text
    assert "Новое имя" in page
    assert "1\u00a0500\u00a0₽" in page


def test_update_sets_individual_member_price(owner, client, student_factory):
    group_id, student_id = _group_with_member(
        owner, student_factory, price_per_lesson=1200
    )

    response = client.post(
        f"/tutor/groups/{group_id}",
        data={
            "name": "A",
            "price": "1200",
            "members_form": "1",
            "members": [student_id],
            f"member_price_{student_id}": "1000",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        member = db.query(GroupMember).filter_by(group_id=group_id).one()
        # Индивидуальная цена участника сохранена, общая цена группы — своя.
        assert member.price_override == 1000
        assert db.get(Group, group_id).price_per_lesson == 1200


def test_update_changes_joined_date(owner, client, student_factory):
    group_id, student_id = _group_with_member(owner, student_factory)

    response = client.post(
        f"/tutor/groups/{group_id}",
        data={
            "name": "A",
            "members_form": "1",
            "members": [student_id],
            f"member_joined_{student_id}": "2026-09-01",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        member = db.query(GroupMember).filter_by(group_id=group_id).one()
        assert member.joined_at.strftime("%Y-%m-%d") == "2026-09-01"

    # Новая дата видна в составе вкладки «Общее».
    html = client.get(f"/tutor/groups/{group_id}/edit").text
    assert "в группе с 01.09.2026" in html


def test_update_adds_new_member(owner, client, student_factory):
    group_id, student_id = _group_with_member(owner, student_factory)
    added = student_factory(tutor_id=owner, first_name="Новый")

    client.post(
        f"/tutor/groups/{group_id}",
        data={"name": "A", "members_form": "1", "members": [student_id, added]},
        headers={"HX-Request": "true"},
    )

    with SessionLocal() as db:
        ids = {
            member.student_id
            for member in db.query(GroupMember).filter_by(group_id=group_id)
        }
    assert ids == {student_id, added}


def test_update_excludes_member_but_keeps_student(owner, client, student_factory):
    """Исключённый участник уходит из группы, карточка ученика цела."""
    group_id, student_id = _group_with_member(owner, student_factory)

    response = client.post(
        f"/tutor/groups/{group_id}",
        data={
            "name": "A",
            "members_form": "1",
            "members": [],
            "removed_members": student_id,
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.query(GroupMember).filter_by(group_id=group_id).count() == 0
        student = db.get(Student, student_id)
        assert student is not None
        assert student.first_name == "Мария"


def test_update_empty_name_returns_modal_with_error(owner, client, student_factory):
    group_id, student_id = _group_with_member(owner, student_factory, name="Прежнее")

    response = client.post(
        f"/tutor/groups/{group_id}",
        data={"name": "  ", "members_form": "1", "members": [student_id]},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Укажите название группы." in response.text
    # Ошибка показывается в модалке, открыта вкладка «Настройки».
    assert "groupManage('settings')" in response.text
    with SessionLocal() as db:
        assert db.get(Group, group_id).name == "Прежнее"


def test_update_over_limit_returns_error(owner, client, student_factory):
    group_id, student_id = _group_with_member(owner, student_factory)
    extra = [student_factory(tutor_id=owner) for _ in range(10)]

    response = client.post(
        f"/tutor/groups/{group_id}",
        data={"name": "A", "members_form": "1", "members": [student_id, *extra]},
        headers={"HX-Request": "true"},
    )
    assert "В группе может быть не более 10 участников." in response.text
    with SessionLocal() as db:
        assert db.query(GroupMember).filter_by(group_id=group_id).count() == 1


def test_update_saves_meeting_url_and_notes(owner, client, student_factory):
    group_id, student_id = _group_with_member(owner, student_factory)

    client.post(
        f"/tutor/groups/{group_id}",
        data={
            "name": "A",
            "members_form": "1",
            "members": [student_id],
            "meeting_url": "https://meet.example.com/a",
            "notes": "Ходить по вторникам",
        },
        headers={"HX-Request": "true"},
    )

    with SessionLocal() as db:
        group = db.get(Group, group_id)
        assert group.meeting_url == "https://meet.example.com/a"
        assert group.notes == "Ходить по вторникам"


def test_update_without_notes_field_keeps_notes(owner, client, student_factory):
    """POST только настроек не стирает заметки, введённые на «Общем»."""
    group_id, student_id = _group_with_member(owner, student_factory)
    with SessionLocal() as db:
        db.get(Group, group_id).notes = "Важные заметки"
        db.commit()

    client.post(
        f"/tutor/groups/{group_id}",
        data={"name": "A", "members_form": "1", "members": [student_id]},
        headers={"HX-Request": "true"},
    )

    with SessionLocal() as db:
        assert db.get(Group, group_id).notes == "Важные заметки"


def test_update_without_htmx_redirects(owner, client, student_factory):
    group_id, student_id = _group_with_member(owner, student_factory)
    response = client.post(
        f"/tutor/groups/{group_id}",
        data={"name": "A", "members_form": "1", "members": [student_id]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/groups"


# --------------------------------------------------------------------------
# Заметки (5.6)
# --------------------------------------------------------------------------


def test_update_notes_saves_and_returns_panel(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)

    response = client.post(
        f"/tutor/groups/{group_id}/notes",
        data={"notes": "Новые заметки"},
    )
    assert response.status_code == 200
    assert "Новые заметки" in response.text
    assert "Заметки сохранены" in response.text
    # Ответ — панель «Общее», а не вся модалка.
    assert 'id="group-general-panel"' in response.text
    assert "<form" not in response.text

    with SessionLocal() as db:
        assert db.get(Group, group_id).notes == "Новые заметки"

    # Заметки видны при следующем открытии.
    html = client.get(f"/tutor/groups/{group_id}/edit").text
    assert "Новые заметки" in html


def test_update_notes_can_clear_notes(owner, client, student_factory):
    group_id, _ = _group_with_member(owner, student_factory)
    with SessionLocal() as db:
        db.get(Group, group_id).notes = "Были заметки"
        db.commit()

    client.post(f"/tutor/groups/{group_id}/notes", data={"notes": "  "})

    with SessionLocal() as db:
        assert db.get(Group, group_id).notes is None


# --------------------------------------------------------------------------
# Изоляция по репетитору (5.7)
# --------------------------------------------------------------------------


@pytest.fixture()
def foreign_group(tutor_factory, student_factory):
    """Группа другого репетитора с участником; возвращает (group_id, student_id)."""
    foreign = tutor_factory(email="groups-manage-foreign@example.com")
    student_id = student_factory(tutor_id=foreign, first_name="Чужойученик")
    with SessionLocal() as db:
        group = Group(tutor_id=foreign, name="Чужая группа")
        db.add(group)
        db.flush()
        db.add(GroupMember(group_id=group.id, student_id=student_id))
        db.commit()
        return group.id, student_id


def test_foreign_group_edit_is_not_found(owner, client, foreign_group):
    group_id, _ = foreign_group
    response = client.get(f"/tutor/groups/{group_id}/edit")
    assert response.status_code == 404
    assert "Чужая группа" not in response.text
    assert "Чужойученик" not in response.text


def test_foreign_group_update_is_not_found(owner, client, foreign_group):
    group_id, student_id = foreign_group
    response = client.post(
        f"/tutor/groups/{group_id}",
        data={"name": "Взломано", "members_form": "1", "members": []},
    )
    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.get(Group, group_id).name == "Чужая группа"
        assert db.query(GroupMember).filter_by(group_id=group_id).count() == 1


def test_foreign_group_notes_is_not_found(owner, client, foreign_group):
    group_id, _ = foreign_group
    response = client.post(
        f"/tutor/groups/{group_id}/notes", data={"notes": "Чужие заметки"}
    )
    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.get(Group, group_id).notes is None


def test_missing_group_is_not_found(owner, client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/tutor/groups/{missing}/edit").status_code == 404
    assert (
        client.post(
            f"/tutor/groups/{missing}", data={"name": "X", "members_form": "1"}
        ).status_code
        == 404
    )
    assert (
        client.post(f"/tutor/groups/{missing}/notes", data={"notes": "X"}).status_code
        == 404
    )


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", "/edit"),
        ("post", ""),
        ("post", "/notes"),
    ],
)
def test_manage_endpoints_require_login(client, foreign_group, method, suffix):
    group_id, _ = foreign_group
    response = getattr(client, method)(
        f"/tutor/groups/{group_id}{suffix}", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
