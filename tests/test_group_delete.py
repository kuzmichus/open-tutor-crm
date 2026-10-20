"""Удаление группы: каскад членства, изоляция, подтверждение (6.1–6.2)."""

import pytest

from app.database import SessionLocal
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.student.models.student import Student

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="groups-delete@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "groups-delete@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _group_with_members(owner, student_factory, count=2):
    """Группа с участниками; возвращает (group_id, [student_id])."""
    student_ids = [
        student_factory(tutor_id=owner, first_name=f"Ученик{index}")
        for index in range(count)
    ]
    with SessionLocal() as db:
        group = Group(tutor_id=owner, name="Удаляемая")
        db.add(group)
        db.flush()
        for student_id in student_ids:
            db.add(GroupMember(group_id=group.id, student_id=student_id))
        db.commit()
        return group.id, student_ids


# --------------------------------------------------------------------------
# Удаление (6.1)
# --------------------------------------------------------------------------


def test_delete_removes_group_and_membership_but_keeps_students(
    owner, client, student_factory
):
    group_id, student_ids = _group_with_members(owner, student_factory)

    response = client.post(
        f"/tutor/groups/{group_id}/delete", headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "group-deleted"
    # Ответ — свежая сетка без удалённой группы.
    assert "Удаляемая" not in response.text
    assert "Групп пока нет" in response.text

    with SessionLocal() as db:
        assert db.get(Group, group_id) is None
        assert db.query(GroupMember).filter_by(group_id=group_id).count() == 0
        # Ученики не тронуты.
        for student_id in student_ids:
            student = db.get(Student, student_id)
            assert student is not None
            assert student.status != "archived"


def test_delete_returns_remaining_groups(owner, client, group_factory):
    """Сетка после удаления содержит оставшиеся карточки."""
    group_factory(tutor_id=owner, name="Остаётся")
    group_id = group_factory(tutor_id=owner, name="Уходит")

    response = client.post(
        f"/tutor/groups/{group_id}/delete", headers={"HX-Request": "true"}
    )
    assert "Остаётся" in response.text
    assert "Уходит" not in response.text


def test_delete_without_htmx_redirects(owner, client, group_factory):
    group_id = group_factory(tutor_id=owner)

    response = client.post(
        f"/tutor/groups/{group_id}/delete", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/groups"
    with SessionLocal() as db:
        assert db.get(Group, group_id) is None


def test_delete_foreign_group_is_not_found(
    owner, client, tutor_factory, student_factory
):
    """Чужая группа недоступна: 404, данные не удаляются."""
    foreign = tutor_factory(email="groups-delete-foreign@example.com")
    student_id = student_factory(tutor_id=foreign)
    with SessionLocal() as db:
        group = Group(tutor_id=foreign, name="Чужая")
        db.add(group)
        db.flush()
        db.add(GroupMember(group_id=group.id, student_id=student_id))
        db.commit()
        group_id = group.id

    response = client.post(f"/tutor/groups/{group_id}/delete")
    assert response.status_code == 404

    with SessionLocal() as db:
        assert db.get(Group, group_id) is not None
        assert db.query(GroupMember).filter_by(group_id=group_id).count() == 1


def test_delete_missing_group_is_not_found(owner, client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/tutor/groups/{missing}/delete").status_code == 404


def test_delete_requires_login(client, group_factory):
    group_id = group_factory()
    response = client.post(
        f"/tutor/groups/{group_id}/delete", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    with SessionLocal() as db:
        assert db.get(Group, group_id) is not None


# --------------------------------------------------------------------------
# Двухшаговое подтверждение (6.2)
# --------------------------------------------------------------------------


def test_modal_footer_has_two_step_delete(owner, client, group_factory):
    """«Удалить» и «Точно удалить?» — две кнопки, POST только у второй."""
    import re

    group_id = group_factory(tutor_id=owner)
    html = client.get(f"/tutor/groups/{group_id}/edit").text

    buttons = re.findall(r"<button[^>]*>.*?</button>", html, flags=re.S)
    first = [b for b in buttons if "confirmingDelete = true" in b]
    second = [b for b in buttons if 'x-show="confirmingDelete"' in b]
    assert len(first) == 1, "нет кнопки «Удалить» первого шага"
    assert len(second) == 1, "нет кнопки «Точно удалить?»"

    # Первый шаг только включает подтверждение — запроса ещё нет.
    assert "hx-post" not in first[0]
    assert "Удалить" in first[0]
    # Второй шаг отправляет POST в сетку и закрывает модалку.
    assert f'hx-post="/tutor/groups/{group_id}/delete"' in second[0]
    assert 'hx-target="#groups-grid"' in second[0]
    assert "Точно удалить?" in second[0]


def test_card_menu_has_two_step_delete(owner, client, group_factory):
    group_id = group_factory(tutor_id=owner)
    html = client.get("/tutor/groups").text

    assert "Удалить" in html
    assert "Точно удалить?" in html
    assert f'data-group-delete="{group_id}"' in html
    assert f'data-group-delete-confirm="{group_id}"' in html
    # Подтверждение отправляет POST в сетку.
    assert f'hx-post="/tutor/groups/{group_id}/delete"' in html
    assert 'hx-target="#groups-grid"' in html


def test_delete_confirmation_has_no_system_dialog(owner, client, group_factory):
    """Системный `confirm()` не используется (решение D7)."""
    group_id = group_factory(tutor_id=owner)
    page = client.get("/tutor/groups").text
    modal = client.get(f"/tutor/groups/{group_id}/edit").text
    assert "confirm(" not in page
    assert "confirm(" not in modal


def test_manage_modal_closes_after_delete(owner, client, group_factory):
    """Модалка управления закрывается по событию удаления."""
    group_id = group_factory(tutor_id=owner)
    html = client.get(f"/tutor/groups/{group_id}/edit").text
    assert '@group-deleted.window="close()"' in html
