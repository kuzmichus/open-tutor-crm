"""Тесты письма восстановления пароля (`send_password_reset_email`).

Транспорт подменяется: проверяем сборку письма — получателя, тему, ссылку
в HTML- и текстовой частях и срок действия из `TTL`.
"""

import pytest

from app.tutor.services import password_reset_email
from app.tutor.services.password_reset import TTL
from app.tutor.services.password_reset_email import SUBJECT, send_password_reset_email

RESET_URL = "https://crm.example.com/tutor/reset-password?key=abc-123"


@pytest.fixture()
def sent(monkeypatch):
    """Перехватывает `send_email` и возвращает список вызовов."""
    calls: list[dict] = []

    def fake_send_email(*, to_email, subject, html, text=None):
        calls.append(
            {"to_email": to_email, "subject": subject, "html": html, "text": text}
        )
        return []

    monkeypatch.setattr(password_reset_email, "send_email", fake_send_email)
    return calls


def test_sends_to_tutor_with_reset_link_in_both_parts(sent):
    errors = send_password_reset_email(
        to_email="tutor@example.com",
        tutor_name="Иван Петров",
        reset_url=RESET_URL,
    )
    assert errors == []
    assert len(sent) == 1

    message = sent[0]
    assert message["to_email"] == "tutor@example.com"
    assert message["subject"] == SUBJECT
    assert RESET_URL in message["html"]
    assert RESET_URL in message["text"]
    # Имя репетитора подставляется в обе части.
    assert "Иван Петров" in message["html"]
    assert "Иван Петров" in message["text"]


def test_ttl_in_message_matches_token_lifetime(sent):
    """Срок в письме — из `TTL` ключа, а не литерал в шаблоне."""
    send_password_reset_email(
        to_email="tutor@example.com", tutor_name="Иван", reset_url=RESET_URL
    )
    hours = int(TTL.total_seconds() // 3600)
    assert f"{hours} ч" in sent[0]["html"]
    assert f"{hours} ч" in sent[0]["text"]


def test_delivery_errors_are_returned(monkeypatch):
    """Ошибка транспорта возвращается списком, а не исключением."""
    monkeypatch.setattr(
        password_reset_email,
        "send_email",
        lambda **kwargs: ["Не удалось связаться с почтовым сервером: timeout"],
    )
    errors = send_password_reset_email(
        to_email="tutor@example.com", tutor_name="Иван", reset_url=RESET_URL
    )
    assert errors == ["Не удалось связаться с почтовым сервером: timeout"]
