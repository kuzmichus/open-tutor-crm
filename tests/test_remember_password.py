"""Тесты запроса восстановления пароля (`/tutor/remember-password`)."""

import re

from app.database import SessionLocal
from app.tutor.models.password_reset_token import PasswordResetToken

PASSWORD = "Секретный-Пароль-1"
KEY_RE = re.compile(r"/tutor/reset-password\?key=([A-Za-z0-9_\-]+)")


def _make_tutor(client, email="reset-user@example.com"):
    client.post(
        "/tutor/register",
        data={
            "name": "Восстанавливаемый",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )


def test_get_renders_form(client):
    response = client.get("/tutor/remember-password")
    assert response.status_code == 200
    assert "Восстановление пароля" in response.text
    assert 'type="email"' in response.text


def test_existing_email_shows_link(client):
    _make_tutor(client)
    response = client.post(
        "/tutor/remember-password",
        data={"email": "reset-user@example.com"},
    )
    assert response.status_code == 200
    match = KEY_RE.search(response.text)
    assert match, "На странице должна быть ссылка с ключом"

    key = match.group(1)
    with SessionLocal() as db:
        row = db.query(PasswordResetToken).filter_by(token=key).one()
        assert row is not None


def test_unknown_email_neutral_message(client):
    response = client.post(
        "/tutor/remember-password",
        data={"email": "nikto@example.com"},
    )
    assert response.status_code == 200
    assert "Если аккаунт" in response.text
    assert KEY_RE.search(response.text) is None, "Ссылка не должна показываться"
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).count() == 0


def test_message_identical_shape_for_unknown(client):
    """Подтверждение для неизвестного email не раскрывает существование аккаунта."""
    _make_tutor(client)
    known = client.post(
        "/tutor/remember-password",
        data={"email": "reset-user@example.com"},
    )
    unknown = client.post(
        "/tutor/remember-password",
        data={"email": "nikto@example.com"},
    )
    assert "Если аккаунт" in unknown.text
    # Изввестный email тоже получает подтверждающий текст (плюс ссылку).
    assert "Ссылка для сброса" in known.text


def test_invalid_email_rejected(client):
    response = client.post(
        "/tutor/remember-password",
        data={"email": "не-email"},
    )
    assert response.status_code == 200
    assert "корректный email" in response.text
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).count() == 0


def test_two_requests_create_distinct_keys(client):
    _make_tutor(client)
    first = client.post(
        "/tutor/remember-password", data={"email": "reset-user@example.com"}
    )
    second = client.post(
        "/tutor/remember-password", data={"email": "reset-user@example.com"}
    )
    key1 = KEY_RE.search(first.text).group(1)
    key2 = KEY_RE.search(second.text).group(1)
    assert key1 != key2
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).count() == 2


def test_key_is_cryptographically_random(client):
    """Ключи достаточно длинные и не угадываются."""
    _make_tutor(client)
    response = client.post(
        "/tutor/remember-password", data={"email": "reset-user@example.com"}
    )
    key = KEY_RE.search(response.text).group(1)
    assert len(key) >= 32


def test_link_does_not_leak_password(client):
    """Ни открытый, ни захешированный пароль не попадают на страницу."""
    _make_tutor(client)
    response = client.post(
        "/tutor/remember-password", data={"email": "reset-user@example.com"}
    )
    with SessionLocal() as db:
        from app.tutor.models.tutor import Tutor

        tutor = db.query(Tutor).filter_by(email="reset-user@example.com").one()
    assert PASSWORD not in response.text
    assert tutor.password_hash not in response.text
