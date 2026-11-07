"""Тесты запроса восстановления пароля (`/tutor/remember-password`)."""

import re

import pytest

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


# ---------------------------------------------------------------------------
# Режим с настроенной почтой (SMTP_HOST задан)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mail_enabled(monkeypatch):
    """Включает почту и перехватывает отправку: сеть в тестах не дёргается."""
    from app.config import settings
    from app.tutor.views import remember_password as view

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "app_base_url", "https://crm.example.com")

    sent: list[dict] = []

    def fake_send(*, to_email, tutor_name, reset_url):
        sent.append({"to_email": to_email, "tutor_name": tutor_name, "reset_url": reset_url})
        return []

    monkeypatch.setattr(view, "send_password_reset_email", fake_send)
    return sent


def test_email_mode_sends_link_and_hides_it(client, mail_enabled):
    """Существующий email: письмо со ссылкой уходит, на странице ссылки нет."""
    _make_tutor(client)
    response = client.post(
        "/tutor/remember-password", data={"email": "reset-user@example.com"}
    )

    assert response.status_code == 200
    assert len(mail_enabled) == 1
    assert mail_enabled[0]["to_email"] == "reset-user@example.com"
    assert mail_enabled[0]["tutor_name"] == "Восстанавливаемый"
    assert mail_enabled[0]["reset_url"].startswith(
        "https://crm.example.com/tutor/reset-password?key="
    )

    # Ссылка не показывается: она ушла письмом.
    assert KEY_RE.search(response.text) is None
    assert "письмо со ссылкой" in response.text

    key = mail_enabled[0]["reset_url"].split("key=")[1]
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).filter_by(token=key).one() is not None


def test_email_mode_unknown_email_sends_nothing(client, mail_enabled):
    """Неизвестный email: письма нет, подтверждение нейтральное."""
    response = client.post(
        "/tutor/remember-password", data={"email": "nikto@example.com"}
    )
    assert response.status_code == 200
    assert mail_enabled == []
    assert "письмо со ссылкой" in response.text
    assert KEY_RE.search(response.text) is None
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).count() == 0


def test_email_mode_failure_does_not_reveal_account(client, mail_enabled, monkeypatch):
    """Сбой отправки: страница та же, что для неизвестного email."""
    from app.tutor.views import remember_password as view

    def failing_send(**kwargs):
        return ["Не удалось связаться с почтовым сервером: timeout"]

    monkeypatch.setattr(view, "send_password_reset_email", failing_send)
    _make_tutor(client)
    response = client.post(
        "/tutor/remember-password", data={"email": "reset-user@example.com"}
    )

    assert response.status_code == 200
    assert "письмо со ссылкой" in response.text
    assert "timeout" not in response.text
    assert KEY_RE.search(response.text) is None


def test_email_mode_link_uses_request_base_when_no_app_base_url(
    client, mail_enabled, monkeypatch
):
    """Без APP_BASE_URL ссылка строится из адреса запроса."""
    from app.config import settings

    monkeypatch.setattr(settings, "app_base_url", "")
    _make_tutor(client)
    client.post("/tutor/remember-password", data={"email": "reset-user@example.com"})

    assert mail_enabled[0]["reset_url"].startswith(
        "http://testserver/tutor/reset-password?key="
    )


def test_email_mode_invalid_email_sends_nothing(client, mail_enabled):
    response = client.post("/tutor/remember-password", data={"email": "не-email"})
    assert "корректный email" in response.text
    assert mail_enabled == []
