"""Тесты регистрации репетитора (`/tutor/register`)."""

import re

from app.common.services.tutor_time import system_zone_name
from app.database import SessionLocal
from app.tutor.models.tutor import Tutor
from app.tutor.services.password_hasher import PasswordHasher

PASSWORD = "Секретный-Пароль-1"

FULL_DATA = {
    "name": "Мария Сидорова",
    "email": "maria@example.com",
    "password": PASSWORD,
    "password_confirm": PASSWORD,
}


def _count_tutors(email: str) -> int:
    with SessionLocal() as db:
        return len(db.query(Tutor).filter_by(email=email).all())


def test_get_renders_form(client):
    response = client.get("/tutor/register")
    assert response.status_code == 200
    assert "Регистрация" in response.text


def test_form_asks_only_name_email_password_and_confirm(client):
    """Форма регистрации запрашивает только имя, email и пароль с подтверждением."""
    response = client.get("/tutor/register")
    field_names = set(re.findall(r'<input[^>]*\bname="([a-z_]+)"', response.text))
    assert field_names == {"name", "email", "password", "password_confirm"}
    # Необязательные поля карточки в форме не запрашиваются.
    for optional in ("phone", "about", "subject", "experience", "hourly_rate", "timezone"):
        assert optional not in field_names


def test_password_confirmation_mismatch_rejected(client):
    before = _count_tutors("maria@example.com")
    response = client.post(
        "/tutor/register",
        data={**FULL_DATA, "password_confirm": "Другой-Пароль"},
    )
    assert response.status_code == 200
    assert "Пароли не совпадают" in response.text
    assert _count_tutors("maria@example.com") == before


def test_missing_confirmation_rejected(client):
    before = _count_tutors("maria@example.com")
    response = client.post(
        "/tutor/register",
        data={**FULL_DATA, "password_confirm": ""},
    )
    assert response.status_code == 200
    assert "Пароли не совпадают" in response.text
    assert _count_tutors("maria@example.com") == before


def test_successful_registration_creates_tutor(client):
    response = client.post("/tutor/register", data=FULL_DATA, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/tutor/login")

    with SessionLocal() as db:
        tutor = db.query(Tutor).filter_by(email="maria@example.com").one()
        assert tutor.name == "Мария Сидорова"
        # Пароль в базе отличается от открытого и проверяется хешером.
        assert tutor.password_hash != FULL_DATA["password"]
        assert PasswordHasher().verify(FULL_DATA["password"], tutor.password_hash)


def test_registration_fills_timezone_with_system_zone(client):
    """Спека (задача 8.1): новый репетитор сразу получает зону.

    Иначе карточка осталась бы с `NULL`, и показ времени падал бы в
    системную зону сервера (design.md D9). Значение — IANA-имя зоны
    (или `UTC`, если системную зону определить не удалось).
    """
    client.post("/tutor/register", data=FULL_DATA, follow_redirects=False)

    with SessionLocal() as db:
        tutor = db.query(Tutor).filter_by(email="maria@example.com").one()
        assert tutor.timezone == (system_zone_name() or "UTC")


def test_password_plaintext_not_stored(client):
    client.post("/tutor/register", data=FULL_DATA)
    with SessionLocal() as db:
        tutor = db.query(Tutor).filter_by(email="maria@example.com").one()
        assert FULL_DATA["password"] not in (tutor.password_hash or "")


def test_extra_post_fields_are_ignored(client):
    """Поля карточки в POST регистрации не принимаются и не сохраняются."""
    response = client.post(
        "/tutor/register",
        data={
            **FULL_DATA,
            "phone": "+7 900 000-00-00",
            "about": "Преподаю 5 лет",
            "subject": "Математика",
            "experience": "ОГЭ, ЕГЭ",
            "hourly_rate": "1500.50",
            "timezone": "Europe/Moscow",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        tutor = db.query(Tutor).filter_by(email="maria@example.com").one()
        assert tutor.phone is None
        assert tutor.about is None
        assert tutor.subject is None
        assert tutor.experience is None
        assert tutor.hourly_rate is None
        # Зона не берётся из формы: подставляется системная (design.md D9).
        assert tutor.timezone != "Europe/Moscow"
        assert tutor.timezone == (system_zone_name() or "UTC")


def test_uuid_ids_are_unique(client):
    client.post("/tutor/register", data=FULL_DATA)
    client.post(
        "/tutor/register",
        data={**FULL_DATA, "email": "petr@example.com", "name": "Пётр"},
    )
    with SessionLocal() as db:
        ids = [t.id for t in db.query(Tutor).all()]
    assert len(ids) >= 2
    assert len(set(ids)) == len(ids)
    assert all(len(i) == 36 for i in ids)


def test_invalid_email_rejected(client):
    before = _count_tutors("bad@example.com")
    response = client.post(
        "/tutor/register",
        data={**FULL_DATA, "email": "не-email"},
    )
    assert response.status_code == 200
    assert "корректный email" in response.text
    assert _count_tutors("bad@example.com") == before


def test_empty_password_rejected(client):
    before = _count_tutors("maria@example.com")
    response = client.post(
        "/tutor/register",
        data={**FULL_DATA, "password": ""},
    )
    assert response.status_code == 200
    assert "Укажите пароль" in response.text
    assert _count_tutors("maria@example.com") == before


def test_duplicate_email_rejected(client):
    client.post("/tutor/register", data=FULL_DATA)
    response = client.post(
        "/tutor/register",
        data={**FULL_DATA, "name": "Другой Человек"},
    )
    assert response.status_code == 200
    assert "уже зарегистрирован" in response.text
    with SessionLocal() as db:
        count = db.query(Tutor).filter_by(email="maria@example.com").count()
    assert count == 1
