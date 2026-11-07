"""Тесты модуля mail: конфигурация SMTP, сборка письма и отправка."""

import smtplib

import pytest

from app.config import Settings
from app.mail.services import sender
from app.mail.services.sender import build_message, email_enabled, send_email


class _FakeSMTP:
    """Заглушка SMTP-клиента: запоминает вызовы, сеть не трогается."""

    instances: list["_FakeSMTP"] = []
    # Исключение, которое бросит `send_message` у следующего клиента.
    next_failure: Exception | None = None

    def __init__(self, host=None, port=None, timeout=None, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.calls: list[tuple] = []
        self.messages = []
        self.fail_with: Exception | None = _FakeSMTP.next_failure
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.calls.append(("ehlo",))

    def starttls(self, context=None):
        self.calls.append(("starttls", context))

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append(("send_message", message))
        self.messages.append(message)


@pytest.fixture()
def smtp(monkeypatch):
    """Подменяет оба класса SMTP и настраивает «включённую» почту."""

    def reset():
        _FakeSMTP.instances = []
        _FakeSMTP.next_failure = None

    reset()
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(sender.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(sender.settings, "smtp_port", 587)
    monkeypatch.setattr(sender.settings, "smtp_username", "bot@example.com")
    monkeypatch.setattr(sender.settings, "smtp_password", "secret")
    monkeypatch.setattr(sender.settings, "smtp_from", "")
    monkeypatch.setattr(sender.settings, "smtp_starttls", True)
    monkeypatch.setattr(sender.settings, "smtp_use_ssl", False)
    monkeypatch.setattr(sender.settings, "smtp_timeout", 15)
    yield _FakeSMTP
    reset()


# --------------------------------------------------------------------------
# Конфигурация
# --------------------------------------------------------------------------

def test_email_disabled_by_default():
    """Пустой SMTP_HOST — почта выключена, приложение работает как раньше."""
    settings = Settings(_env_file=None)
    assert settings.email_enabled is False
    assert settings.smtp_port == 587
    assert settings.smtp_starttls is True


def test_mail_from_falls_back_to_username():
    """SMTP_FROM пуст — отправитель совпадает с логином."""
    settings = Settings(
        _env_file=None, smtp_host="smtp.example.com", smtp_username="bot@example.com"
    )
    assert settings.mail_from == "bot@example.com"
    assert settings.email_enabled is True


def test_mail_from_prefers_explicit_value():
    settings = Settings(
        _env_file=None,
        smtp_host="smtp.example.com",
        smtp_username="bot@example.com",
        smtp_from="no-reply@example.com",
    )
    assert settings.mail_from == "no-reply@example.com"


def test_smtp_host_requires_sender():
    """SMTP_HOST без отправителя — ошибка старта с именами параметров."""
    with pytest.raises(ValueError) as exc:
        Settings(_env_file=None, smtp_host="smtp.example.com")
    message = str(exc.value)
    assert "SMTP_FROM" in message
    assert "SMTP_USERNAME" in message


def test_smtp_ssl_and_starttls_are_exclusive():
    with pytest.raises(ValueError) as exc:
        Settings(
            _env_file=None,
            smtp_host="smtp.example.com",
            smtp_username="bot@example.com",
            smtp_use_ssl=True,
            smtp_starttls=True,
        )
    assert "взаимоисключающи" in str(exc.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [("smtp_port", 0), ("smtp_timeout", 0)],
)
def test_smtp_rejects_non_positive_numbers(field, value):
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            smtp_host="smtp.example.com",
            smtp_username="bot@example.com",
            **{field: value},
        )


# --------------------------------------------------------------------------
# Сборка письма
# --------------------------------------------------------------------------

def test_build_message_has_recipient_subject_and_both_parts(monkeypatch):
    monkeypatch.setattr(sender.settings, "smtp_from", "bot@example.com")
    message = build_message(
        to_email="user@example.com",
        subject="Сброс пароля",
        html="<p>Ссылка: https://crm.example.com/reset?key=abc</p>",
        text="Ссылка: https://crm.example.com/reset?key=abc",
    )
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Сброс пароля"
    assert "bot@example.com" in message["From"]
    assert message["Message-ID"].endswith("@example.com>")

    body = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "reset?key=abc" in body
    assert "reset?key=abc" in html


def test_build_message_without_text_uses_fallback(monkeypatch):
    monkeypatch.setattr(sender.settings, "smtp_from", "bot@example.com")
    message = build_message(
        to_email="user@example.com", subject="Тема", html="<p>Привет</p>"
    )
    body = message.get_body(preferencelist=("plain",)).get_content()
    assert body.strip() == sender.PLAIN_FALLBACK


# --------------------------------------------------------------------------
# Отправка
# --------------------------------------------------------------------------

def test_send_email_returns_error_when_disabled(monkeypatch):
    monkeypatch.setattr(sender.settings, "smtp_host", "")
    errors = send_email(to_email="user@example.com", subject="Т", html="<p>Т</p>")
    assert len(errors) == 1
    assert "не настроена" in errors[0]


def test_send_email_delivers_over_starttls(smtp):
    errors = send_email(
        to_email="user@example.com",
        subject="Сброс пароля",
        html="<p>Ссылка</p>",
        text="Ссылка",
    )
    assert errors == []

    client = smtp.instances[0]
    assert client.host == "smtp.example.com"
    assert client.port == 587
    assert client.timeout == 15
    # STARTTLS до логина, логин до отправки.
    assert [call[0] for call in client.calls] == [
        "ehlo",
        "starttls",
        "ehlo",
        "login",
        "send_message",
    ]
    assert client.calls[3] == ("login", "bot@example.com", "secret")
    assert client.messages[0]["To"] == "user@example.com"


def test_send_email_uses_ssl_without_starttls(smtp, monkeypatch):
    monkeypatch.setattr(sender.settings, "smtp_use_ssl", True)
    monkeypatch.setattr(sender.settings, "smtp_starttls", False)
    monkeypatch.setattr(sender.settings, "smtp_port", 465)

    errors = send_email(to_email="user@example.com", subject="Т", html="<p>Т</p>")
    assert errors == []
    client = smtp.instances[0]
    assert client.port == 465
    assert [call[0] for call in client.calls] == ["ehlo", "login", "send_message"]


def test_send_email_without_credentials_skips_login(smtp, monkeypatch):
    """Локальный SMTP без авторизации: логин не вызывается."""
    monkeypatch.setattr(sender.settings, "smtp_username", "")
    monkeypatch.setattr(sender.settings, "smtp_from", "no-reply@example.com")

    errors = send_email(to_email="user@example.com", subject="Т", html="<p>Т</p>")
    assert errors == []
    assert [call[0] for call in smtp.instances[0].calls] == ["ehlo", "starttls", "ehlo", "send_message"]


def test_send_email_returns_smtp_error(smtp):
    smtp.next_failure = smtplib.SMTPRecipientsRefused({"user@example.com": (550, b"no")})
    errors = send_email(to_email="user@example.com", subject="Т", html="<p>Т</p>")
    assert len(errors) == 1
    assert "отклонил письмо" in errors[0]


def test_send_email_returns_network_error(smtp):
    smtp.next_failure = OSError("connection refused")
    errors = send_email(to_email="user@example.com", subject="Т", html="<p>Т</p>")
    assert len(errors) == 1
    assert "связаться" in errors[0]


def test_send_email_requires_recipient(smtp):
    assert send_email(to_email="  ", subject="Т", html="<p>Т</p>") == [
        "Не указан получатель письма."
    ]
    assert smtp.instances == []


def test_send_email_requires_subject(smtp):
    assert send_email(to_email="user@example.com", subject="", html="<p>Т</p>") == [
        "Не указана тема письма."
    ]
    assert smtp.instances == []


def test_email_enabled_reads_settings(monkeypatch):
    monkeypatch.setattr(sender.settings, "smtp_host", "smtp.example.com")
    assert email_enabled() is True
    monkeypatch.setattr(sender.settings, "smtp_host", "")
    assert email_enabled() is False
