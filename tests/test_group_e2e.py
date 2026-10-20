"""Сквозной сценарий групп: создание → состав → вкладки → правки → удаление (7.3).

Тест идёт через HTTP-клиент, как пользователь: модалки запрашиваются теми же
маршрутами, формы отправляются теми же полями, сетка проверяется по тексту.
"""

import html
import json
import re

import pytest

from app.database import SessionLocal
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.student.models.student import Student

PASSWORD = "Секретный-Пароль-1"


def _attr_json(markup: str, name: str) -> object:
    match = re.search(rf"""{name}=(?:'([^']*)'|"([^"]*)")""", markup)
    assert match, f"нет атрибута {name}"
    raw = match.group(1) if match.group(1) is not None else match.group(2)
    return json.loads(html.unescape(raw))


@pytest.fixture()
def owner(client, tutor_factory):
    tutor_id = tutor_factory(email="groups-e2e@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "groups-e2e@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def test_full_group_lifecycle(owner, client, student_factory):
    """Полный цикл: создание, состав, пять вкладок, правки, удаление."""
    first = student_factory(tutor_id=owner, first_name="Мария")
    second = student_factory(tutor_id=owner, first_name="Иван")

    # 1. Список пуст.
    page = client.get("/tutor/groups")
    assert "Групп пока нет" in page.text

    # 2. Модалка создания открывается, ученики доступны в выборе.
    modal = client.get("/tutor/groups/new")
    assert modal.status_code == 200
    options = _attr_json(modal.text, "data-options")
    assert {option["id"] for option in options} == {first, second}

    # 3. Создание группы с участниками.
    created = client.post(
        "/tutor/groups",
        data={
            "name": "Математика 9А",
            "price": "1200",
            "description": "Подготовка к ОГЭ",
            "members_form": "1",
            "members": [first, second],
            f"member_joined_{first}": "2026-09-01",
        },
        headers={"HX-Request": "true"},
    )
    assert created.status_code == 200
    assert created.headers["HX-Trigger"] == "group-saved"

    with SessionLocal() as db:
        group = db.query(Group).filter_by(tutor_id=owner).one()
        group_id = group.id

    # 4. Карточка в списке: название, описание, счётчик, цена.
    page = client.get("/tutor/groups").text
    assert "Математика 9А" in page
    assert "Подготовка к ОГЭ" in page
    assert "2 / 10 учеников" in page
    assert "1\u00a0200\u00a0₽" in page

    # 5. Модалка управления: пять вкладок, состав с датами.
    manage = client.get(f"/tutor/groups/{group_id}/edit")
    assert manage.status_code == 200
    assert "Группа Математика 9А" in manage.text
    assert "Группа · участников: 2" in manage.text
    assert manage.text.count('role="tab"') == 5
    assert "в группе с 01.09.2026" in manage.text
    assert "Состав (2)" in manage.text

    # 6. Добавление нового ученика из мини-формы прямо в форме группы.
    mini = client.post(
        "/tutor/groups/students",
        data={"first_name": "Пётр", "last_name": "Сидоров", "phone": "8 916 123-45-67"},
    )
    assert mini.status_code == 200
    member = _attr_json(mini.text, "data-member")
    assert member["name"] == "Пётр Сидоров"
    new_student_id = member["id"]
    # Созданный ученик уже в составе формы — в опциях его нет.
    options = _attr_json(mini.text, "data-options")
    assert new_student_id not in [option["id"] for option in options]

    # 7. Сохранение настроек: состав с новым учеником, индивидуальные цены.
    saved = client.post(
        f"/tutor/groups/{group_id}",
        data={
            "name": "Математика 9А (вечер)",
            "price": "1500",
            "description": "Подготовка к ОГЭ",
            "members_form": "1",
            "members": [first, second, new_student_id],
            f"member_price_{second}": "1000",
        },
        headers={"HX-Request": "true"},
    )
    assert saved.status_code == 200
    assert saved.headers["HX-Trigger"] == "group-saved"

    with SessionLocal() as db:
        group = db.get(Group, group_id)
        assert group.name == "Математика 9А (вечер)"
        assert group.price_per_lesson == 1500
        members = {
            m.student_id: m
            for m in db.query(GroupMember).filter_by(group_id=group_id)
        }
    assert set(members) == {first, second, new_student_id}
    assert members[second].price_override == 1000
    assert members[first].price_override is None

    # 8. Заметки сохраняются отдельным запросом с подменой панели.
    notes = client.post(
        f"/tutor/groups/{group_id}/notes",
        data={"notes": "Ходить по вторникам"},
    )
    assert notes.status_code == 200
    assert "Заметки сохранены" in notes.text
    assert 'id="group-general-panel"' in notes.text

    manage = client.get(f"/tutor/groups/{group_id}/edit").text
    assert "Ходить по вторникам" in manage
    assert "3 из 10" in manage
    assert "Состав (3)" in manage

    # 9. Изменение состава: второй ученик исключён, ученик цел.
    client.post(
        f"/tutor/groups/{group_id}",
        data={
            "name": "Математика 9А (вечер)",
            "price": "1500",
            "members_form": "1",
            "members": [first, new_student_id],
        },
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as db:
        remaining = {
            m.student_id
            for m in db.query(GroupMember).filter_by(group_id=group_id)
        }
        assert db.get(Student, second) is not None
    assert remaining == {first, new_student_id}

    # 10. Удаление: группа и членство уходят, ученики остаются.
    deleted = client.post(
        f"/tutor/groups/{group_id}/delete", headers={"HX-Request": "true"}
    )
    assert deleted.status_code == 200
    assert deleted.headers["HX-Trigger"] == "group-deleted"
    assert "Групп пока нет" in deleted.text

    with SessionLocal() as db:
        assert db.get(Group, group_id) is None
        assert db.query(GroupMember).filter_by(group_id=group_id).count() == 0
        for student_id in (first, second, new_student_id):
            assert db.get(Student, student_id) is not None

    # 11. Список снова пуст, ошибок нет.
    page = client.get("/tutor/groups")
    assert page.status_code == 200
    assert "Групп пока нет" in page.text
