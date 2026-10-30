"""Тесты подсказки логина в модалке «Доступ ученика» (D7 change'а
student-cabinet-access): транслит первой буквы имени и фамилии, суффикс
при занятости, предзаполнение формы для ученика без входа.
"""

import pytest

from app.database import SessionLocal
from app.student.models.student import Student
from app.student.models.student_access import StudentAccess
from app.student.services.credentials import suggest_login


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="hint-owner@example.com", password="Пароль-1")
    client.post(
        "/tutor/login",
        data={"email": "hint-owner@example.com", "password": "Пароль-1"},
        follow_redirects=False,
    )
    return tutor_id


def test_suggest_login_transliterates(client, tutor_factory, student_factory):
    tutor_id = tutor_factory()
    ivan = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Петров")
    with SessionLocal() as db:
        student = db.get(Student, ivan)
        assert suggest_login(db, student) == "ipetrov"


def test_suggest_login_without_last_name(client, tutor_factory, student_factory):
    tutor_id = tutor_factory()
    ivan = student_factory(tutor_id=tutor_id, first_name="Иван", last_name=None)
    with SessionLocal() as db:
        student = db.get(Student, ivan)
        assert suggest_login(db, student) == "ivan"


def test_suggest_login_non_cyrillic_is_empty(client, tutor_factory, student_factory):
    tutor_id = tutor_factory()
    john = student_factory(tutor_id=tutor_id, first_name="John", last_name="Smith")
    with SessionLocal() as db:
        student = db.get(Student, john)
        assert suggest_login(db, student) == ""


def test_suggest_login_suffix_when_taken(client, tutor_factory, student_factory):
    tutor_id = tutor_factory()
    first = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Петров")
    second = student_factory(tutor_id=tutor_id, first_name="Игорь", last_name="Петров")
    with SessionLocal() as db:
        db.add(
            StudentAccess(
                student_id=first,
                login="ipetrov",
                password_hash="pbkdf2_sha256$1$placeholder$placeholder",
            )
        )
        db.commit()
        student = db.get(Student, second)
        assert suggest_login(db, student) == "ipetrov1"


def test_access_modal_prefills_hint_for_new_access(client, owner, student_factory):
    """Форма модалки без входа предзаполнена подсказкой из имени."""
    student_id = student_factory(tutor_id=owner, first_name="Маша", last_name="Иванова")
    page = client.get(f"/tutor/students/{student_id}/access").text

    assert 'value="mivanova"' in page


def test_access_modal_keeps_login_for_existing_access(client, owner, student_factory):
    """Вход уже создан — показывается его логин, подсказка не считается."""
    student_id = student_factory(tutor_id=owner, first_name="Маша", last_name="Иванова")
    client.post(
        f"/tutor/students/{student_id}/access",
        data={"login": "masha_custom", "password": "пароль-пароль"},
        headers={"HX-Request": "true"},
    )
    page = client.get(f"/tutor/students/{student_id}/access").text

    assert 'value="masha_custom"' in page
    assert "mivanova" not in page
