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


def test_existing_email_creates_key_but_hides_link(client):
    """Ключ создаётся, но ссылка на странице не показывается."""
    _make_tutor(client)
    response = client.post(
        "/tutor/remember-password",
        data={"email": "reset-user@example.com"},
    )
    assert response.status_code == 200
    assert KEY_RE.search(response.text) is None, "Ссылка не должна показываться"
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).count() == 1


def test_unknown_email_neutral_message(client):
    response = client.post(
        "/tutor/remember-password",
        data={"email": "nikto@example.com"},
    )
    assert response.status_code == 200
    assert "Если аккаунт" in response.text or "не настроена" in response.text
    assert KEY_RE.search(response.text) is None, "Ссылка не должна показываться"
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).count() == 0


def test_message_identical_shape_for_known_and_unknown(client):
    """Ответ не раскрывает, существует ли аккаунт: тексты совпадают."""
    _make_tutor(client)
    known = client.post(
        "/tutor/remember-password",
        data={"email": "reset-user@example.com"},
    )
    unknown = client.post(
        "/tutor/remember-password",
        data={"email": "nikto@example.com"},
    )
    assert KEY_RE.search(known.text) is None
    assert KEY_RE.search(unknown.text) is None
    # Почта не настроена — один и тот же блок в обоих ответах.
    assert "не настроена" in known.text and "не настроена" in unknown.text


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
    client.post("/tutor/remember-password", data={"email": "reset-user@example.com"})
    client.post("/tutor/remember-password", data={"email": "reset-user@example.com"})
    with SessionLocal() as db:
        keys = [row.token for row in db.query(PasswordResetToken).all()]
    assert len(keys) == 2
    assert keys[0] != keys[1]


def test_key_is_cryptographically_random(client):
    """Ключи достаточно длинные и не угадываются."""
    _make_tutor(client)
    client.post("/tutor/remember-password", data={"email": "reset-user@example.com"})
    with SessionLocal() as db:
        key = db.query(PasswordResetToken).one().token
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
# Почта не настроена (режим по умолчанию)
# ---------------------------------------------------------------------------


def test_mail_off_explains_recovery_unavailable(client, caplog):
    """Без SMTP ссылки нет: страница говорит о ненастроенной почте."""
    _make_tutor(client)
    response = client.post(
        "/tutor/remember-password", data={"email": "reset-user@example.com"}
    )
    assert response.status_code == 200
    assert "не настроена" in response.text
    assert KEY_RE.search(response.text) is None


def test_mail_off_writes_link_to_log(client, caplog):
    """Ссылка уходит в лог: владелец сервера может помочь вручную."""
    _make_tutor(client)
    with caplog.at_level("WARNING", logger="mail"):
        client.post(
            "/tutor/remember-password", data={"email": "reset-user@example.com"}
        )
    with SessionLocal() as db:
        key = db.query(PasswordResetToken).one().token
    assert key in caplog.text


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
