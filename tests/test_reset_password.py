"""Тесты установки нового пароля по ключу (`/tutor/reset-password`)."""

import re
from datetime import timedelta

from app.database import SessionLocal
from app.tutor.models.password_reset_token import PasswordResetToken
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow
from app.tutor.services.password_hasher import PasswordHasher
from app.tutor.views.reset_password import INVALID_LINK

PASSWORD = "Старый-Пароль-1"
NEW_PASSWORD = "Новый-Пароль-2"
KEY_RE = re.compile(r"/tutor/reset-password\?key=([A-Za-z0-9_\-]+)")


def _setup(client, email="reset-user@example.com"):
    """Создаёт аккаунт и запрашивает ключ; возвращает ключ."""
    client.post(
        "/tutor/register",
        data={
            "name": "Восстанавливаемый",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )
    response = client.post(
        "/tutor/remember-password", data={"email": email}
    )
    return KEY_RE.search(response.text).group(1)


def _password_hash(email: str) -> str | None:
    with SessionLocal() as db:
        tutor = db.query(Tutor).filter_by(email=email).one()
        return tutor.password_hash


def test_get_renders_form_for_valid_key(client):
    key = _setup(client)
    response = client.get(f"/tutor/reset-password?key={key}")
    assert response.status_code == 200
    assert "Установка нового пароля" in response.text
    assert 'name="password"' in response.text


def test_successful_reset_changes_password(client):
    key = _setup(client)
    response = client.post(
        "/tutor/reset-password",
        data={"key": key, "password": NEW_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/tutor/login")

    stored = _password_hash("reset-user@example.com")
    assert PasswordHasher().verify(NEW_PASSWORD, stored)
    assert PasswordHasher().verify(PASSWORD, stored) is False


def test_old_password_rejected_after_reset(client):
    key = _setup(client)
    client.post(
        "/tutor/reset-password",
        data={"key": key, "password": NEW_PASSWORD},
    )
    response = client.post(
        "/tutor/login",
        data={"email": "reset-user@example.com", "password": PASSWORD},
    )
    assert "Неверный email или пароль" in response.text


def test_new_password_works_for_login(client):
    key = _setup(client)
    client.post(
        "/tutor/reset-password",
        data={"key": key, "password": NEW_PASSWORD},
    )
    response = client.post(
        "/tutor/login",
        data={"email": "reset-user@example.com", "password": NEW_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/"


def test_key_single_use(client):
    """Повторное использование ключа отклоняется и не меняет пароль."""
    key = _setup(client)
    client.post(
        "/tutor/reset-password",
        data={"key": key, "password": NEW_PASSWORD},
    )
    before = _password_hash("reset-user@example.com")

    response = client.post(
        "/tutor/reset-password",
        data={"key": key, "password": "Совсем-Другой-3"},
    )
    assert response.status_code == 200
    assert INVALID_LINK in response.text
    assert _password_hash("reset-user@example.com") == before


def test_unknown_key_rejected(client):
    response = client.get("/tutor/reset-password?key=нет-такого")
    assert response.status_code == 200
    assert INVALID_LINK in response.text
    # Форма нового пароля не предлагается.
    assert 'name="password"' not in response.text


def test_unknown_key_post_does_not_change_password(client):
    key = _setup(client)
    before = _password_hash("reset-user@example.com")
    response = client.post(
        "/tutor/reset-password",
        data={"key": "нет-такого", "password": NEW_PASSWORD},
    )
    assert INVALID_LINK in response.text
    assert _password_hash("reset-user@example.com") == before


def test_empty_new_password_rejected(client):
    key = _setup(client)
    before = _password_hash("reset-user@example.com")
    response = client.post(
        "/tutor/reset-password",
        data={"key": key, "password": ""},
    )
    assert response.status_code == 200
    assert "Укажите новый пароль" in response.text
    assert _password_hash("reset-user@example.com") == before


def test_key_marked_used_after_reset(client):
    key = _setup(client)
    client.post(
        "/tutor/reset-password",
        data={"key": key, "password": NEW_PASSWORD},
    )
    with SessionLocal() as db:
        row = db.query(PasswordResetToken).filter_by(token=key).one()
        assert row.used_at is not None


def test_expired_key_get_rejected(client, tutor_factory):
    """(Задача 4.3) Истёкший ключ: GET — сообщение без формы."""
    email = "expired@example.com"
    tutor_factory(email=email, password=PASSWORD)
    client.post("/tutor/remember-password", data={"email": email})

    # Прорастить срок действия ключа в прошлое.
    with SessionLocal() as db:
        row = db.query(PasswordResetToken).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        key = row.token

    response = client.get(f"/tutor/reset-password?key={key}")
    assert response.status_code == 200
    assert INVALID_LINK in response.text
    assert 'name="password"' not in response.text


def test_expired_key_post_does_not_change_password(client, tutor_factory):
    """(Задача 4.3) Истёкший ключ: POST не меняет пароль."""
    email = "expired2@example.com"
    tutor_factory(email=email, password=PASSWORD)
    client.post("/tutor/remember-password", data={"email": email})

    with SessionLocal() as db:
        row = db.query(PasswordResetToken).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        key = row.token

    before = _password_hash(email)
    response = client.post(
        "/tutor/reset-password",
        data={"key": key, "password": NEW_PASSWORD},
    )
    assert INVALID_LINK in response.text
    assert _password_hash(email) == before


def test_new_password_never_leaked(client):
    key = _setup(client)
    response = client.get(f"/tutor/reset-password?key={key}")
    assert PASSWORD not in response.text
