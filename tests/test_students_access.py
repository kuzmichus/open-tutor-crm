"""Тесты доступа ученика: модалка логина/пароля, уникальность, один показ.

change student-list-reference: кнопка «Доступ» открывает модалку; вход
хранится хешем и показывается один раз; логин уникален глобально —
личный кабинет ученика будет входить без указания репетитора.
"""

import pytest

from app.database import SessionLocal
from app.student.models.student_access import StudentAccess
from app.student.services.credentials import (
    ERROR_LOGIN_FORMAT,
    ERROR_LOGIN_TAKEN,
    ERROR_PASSWORD_SHORT,
    generate_password,
    validate_login,
    validate_password,
)
from app.tutor.services.password_hasher import PasswordHasher

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="access-owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "access-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


# --------------------------------------------------------------------------
# Валидация (сервис)
# --------------------------------------------------------------------------


def test_validate_login_rules():
    """Логин: латиница/цифры/подчёркивание, минимум 3 символа."""
    assert validate_login("petya") == []
    assert validate_login("Pe_1") == []
    for bad in ("ab", "", "кот", "petya Ivan", "petya!", "petya-ivan"):
        assert validate_login(bad) == [ERROR_LOGIN_FORMAT]


def test_validate_password_rules():
    assert validate_password("длинный-пароль") == []
    assert validate_password("короче8") == [ERROR_PASSWORD_SHORT]
    assert validate_password("") == [ERROR_PASSWORD_SHORT]


def test_generate_password_is_safe_alphabet():
    """Пароль генерируется без похожих символов и нужной длины."""
    for _ in range(20):
        value = generate_password()
        assert len(value) == 12
        assert set(value) <= set(
            "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
        )
        assert not (set(value) & set("0Oo1lI"))


# --------------------------------------------------------------------------
# Модалка и сохранение
# --------------------------------------------------------------------------


def test_access_modal_shows_notice_when_no_access(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    page = client.get(f"/tutor/students/{student_id}/access").text

    assert "Доступ ученика (логин/пароль)" in page
    assert "ещё нет входа" in page
    assert 'name="login"' in page
    assert 'name="password"' in page
    assert "Сгенерировать" in page
    assert "studentAccess" in page or "x-ref=\"password\"" in page


def test_access_save_creates_access_and_shows_credentials_once(
    client, owner, student_factory
):
    """Успех: вход создан, логин и пароль показаны один раз, в БД — хеш."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    response = client.post(
        f"/tutor/students/{student_id}/access",
        data={"login": "masha", "password": "пароль-пароль"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Вход создан" in response.text
    assert "masha" in response.text
    assert "пароль-пароль" in response.text  # единственный показ
    assert "Данные показываются один раз" in response.text

    with SessionLocal() as db:
        access = db.query(StudentAccess).filter_by(student_id=student_id).one()
        assert access.login == "masha"
        assert access.password_hash != "пароль-пароль"
        assert PasswordHasher().verify("пароль-пароль", access.password_hash)


def test_access_modal_after_creation_hides_password(client, owner, student_factory):
    """Повторное открытие: логин виден, пароля нет — только смена."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    client.post(
        f"/tutor/students/{student_id}/access",
        data={"login": "masha", "password": "пароль-пароль"},
        headers={"HX-Request": "true"},
    )
    page = client.get(f"/tutor/students/{student_id}/access").text

    assert "уже создан" in page
    assert "пароль-пароль" not in page
    assert "не менять" in page


def test_access_save_keeps_password_when_empty(client, owner, student_factory):
    """Пустой пароль при существующем входе меняет только логин, не пароль."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    client.post(
        f"/tutor/students/{student_id}/access",
        data={"login": "masha", "password": "пароль-пароль"},
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as db:
        old_hash = db.get(StudentAccess, db.query(StudentAccess).filter_by(
            student_id=student_id).one().id).password_hash

    response = client.post(
        f"/tutor/students/{student_id}/access",
        data={"login": "masha_new", "password": ""},
        headers={"HX-Request": "true"},
    )
    assert "Вход создан" in response.text

    with SessionLocal() as db:
        access = db.query(StudentAccess).filter_by(student_id=student_id).one()
        assert access.login == "masha_new"
        assert access.password_hash == old_hash


def test_access_save_rejects_bad_values(client, owner, student_factory):
    """Ошибки валидации возвращают форму с сообщениями, записи нет."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    response = client.post(
        f"/tutor/students/{student_id}/access",
        data={"login": "кот", "password": "пароль"},
        headers={"HX-Request": "true"},
    )
    assert ERROR_LOGIN_FORMAT in response.text
    assert ERROR_PASSWORD_SHORT in response.text

    with SessionLocal() as db:
        assert db.query(StudentAccess).filter_by(student_id=student_id).count() == 0


def test_access_login_is_globally_unique(client, owner, tutor_factory,
                                         student_factory):
    """Логин занят другим учеником (даже того же репетитора) — отказ."""
    first = student_factory(tutor_id=owner, first_name="Маша")
    second = student_factory(tutor_id=owner, first_name="Второй")
    client.post(
        f"/tutor/students/{first}/access",
        data={"login": "shared", "password": "пароль-пароль"},
        headers={"HX-Request": "true"},
    )

    response = client.post(
        f"/tutor/students/{second}/access",
        data={"login": "shared", "password": "пароль-пароль"},
        headers={"HX-Request": "true"},
    )
    assert ERROR_LOGIN_TAKEN in response.text

    with SessionLocal() as db:
        assert db.query(StudentAccess).filter_by(student_id=second).count() == 0


def test_access_save_requires_login(client, student_factory, tutor_factory):
    """Без сессии сохранение не применяется — редирект на вход."""
    tutor_id = tutor_factory(email="access-anon@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    response = client.post(
        f"/tutor/students/{student_id}/access",
        data={"login": "masha", "password": "пароль-пароль"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    with SessionLocal() as db:
        assert db.query(StudentAccess).count() == 0


def test_access_isolation(client, owner, tutor_factory, student_factory):
    """Чужой ученик и несуществующий неразличимы — 404."""
    other_id = tutor_factory(email="access-other@example.com")
    foreign = student_factory(tutor_id=other_id, first_name="Чужой")

    assert client.get(f"/tutor/students/{foreign}/access").status_code == 404
    assert client.get("/tutor/students/нет-такого/access").status_code == 404

    response = client.post(
        f"/tutor/students/{foreign}/access",
        data={"login": "hacked", "password": "пароль-пароль"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.query(StudentAccess).filter_by(login="hacked").count() == 0


def test_access_without_htmx_redirects(client, owner, student_factory):
    """Без JS — 303 на список: форма работает и без htmx."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    response = client.post(
        f"/tutor/students/{student_id}/access",
        data={"login": "masha", "password": "пароль-пароль"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/students"
