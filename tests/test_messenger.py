"""Тесты модуля messenger: реестр, подключения, отправка, декораторы.

HTTP-транспорт подменяется (monkeypatch на `urllib.request.urlopen`):
сеть в тестах не дёргается, но путь вызова — тот же, что в бою.
"""

import io
import json
import urllib.error
import urllib.request

import pytest

from app.database import SessionLocal
from app.messenger.services.connections import (
    connected_messengers,
    is_messenger_connected,
)
from app.messenger.services.errors import SendError
from app.messenger.services.logging_sender import LoggingSender
from app.messenger.services.max_sender import MaxSender
from app.messenger.services.messengers import token_key
from app.messenger.services.registry import get_sender_class, registered_messengers
from app.messenger.services.retry_sender import RetrySender
from app.messenger.services.send import send_message
from app.messenger.services.telegram_sender import TelegramSender
from app.tutor.services.params import set_param

TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
MAX_TOKEN = "pKcfaXfFUnfTSMPSYJjpdHHnPEMucRQGxFYEXhIq"
CHAT_ID = "100200300"


# ---------------------------------------------------------------------------
# Вспомогательное: подмена HTTP-транспорта
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Минимальный ответ urlopen: context manager с JSON-телом."""

    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, responder, calls):
    """Подменяет urlopen; каждый вызов дописывается в список `calls`."""

    def fake_urlopen(request, timeout=None, context=None):
        calls.append({
            "url": request.full_url,
            "data": json.loads(request.data.decode()),
            "headers": dict(request.header_items()),
            # verify_mode: 2 = CERT_REQUIRED (проверка), 0 = CERT_NONE.
            "tls_verify": context is None or context.verify_mode != 0,
        })
        return responder(calls[-1])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _connect(db, tutor_id, token=TOKEN):
    set_param(db, tutor_id, token_key("telegram"), token)


# ---------------------------------------------------------------------------
# Реестр отправителей
# ---------------------------------------------------------------------------


def test_telegram_sender_registered():
    assert "telegram" in registered_messengers()
    assert get_sender_class("telegram") is TelegramSender


def test_max_sender_registered():
    assert get_sender_class("max") is MaxSender


def test_unknown_messenger_has_no_sender():
    assert get_sender_class("whatsapp") is None


# ---------------------------------------------------------------------------
# Статусы подключения
# ---------------------------------------------------------------------------


def test_connected_messengers_empty_by_default(client, tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        assert connected_messengers(db, tutor_id) == []
        assert is_messenger_connected(db, tutor_id, "telegram") is False


def test_connected_messengers_lists_connected(client, tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect(db, tutor_id)
        assert connected_messengers(db, tutor_id) == ["telegram"]
        assert is_messenger_connected(db, tutor_id, "telegram") is True
        assert is_messenger_connected(db, tutor_id, "max") is False


def test_connected_ignores_unknown_messenger(client, tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        assert is_messenger_connected(db, tutor_id, "whatsapp") is False


def test_connections_isolated_by_tutor(client, tutor_factory):
    """Токен репетитора A не делает подключённым репетитора B."""
    tutor_a = tutor_factory()
    tutor_b = tutor_factory()
    with SessionLocal() as db:
        _connect(db, tutor_a)
        assert connected_messengers(db, tutor_b) == []


# ---------------------------------------------------------------------------
# send_message: валидация без сети
# ---------------------------------------------------------------------------


def test_send_unknown_messenger(client, tutor_factory, monkeypatch):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        errors = send_message(db, tutor_id, "whatsapp", CHAT_ID, "привет")

    assert errors and "Неизвестный мессенджер" in errors[0]


def test_send_unsupported_messenger(client, tutor_factory, monkeypatch):
    """Мессенджер из списка без реализованного отправителя."""
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        errors = send_message(db, tutor_id, "vk", CHAT_ID, "привет")

    assert errors and "не поддерживается" in errors[0]


def test_send_without_connection(client, tutor_factory, monkeypatch):
    """Не подключён — ошибка, HTTP-запрос не выполняется."""
    calls = []

    def fail(*args, **kwargs):
        raise AssertionError("сеть не должна вызываться")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        errors = send_message(db, tutor_id, "telegram", CHAT_ID, "привет")

    assert errors and "не подключён" in errors[0]
    assert calls == []


def test_send_requires_recipient_and_text(client, tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect(db, tutor_id)

        no_recipient = send_message(db, tutor_id, "telegram", "  ", "привет")
        assert no_recipient and "получатель" in no_recipient[0]

        no_text = send_message(db, tutor_id, "telegram", CHAT_ID, "   ")
        assert no_text and "текст" in no_text[0].lower()


# ---------------------------------------------------------------------------
# send_message: доставка (HTTP подменён)
# ---------------------------------------------------------------------------


def test_send_success(client, tutor_factory, monkeypatch):
    calls = []
    _patch_urlopen(
        monkeypatch,
        lambda call: _FakeResponse({"ok": True, "result": {"message_id": 1}}),
        calls,
    )
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect(db, tutor_id)
        errors = send_message(db, tutor_id, "telegram", CHAT_ID, "Привет!")

    assert errors == []
    assert len(calls) == 1
    # Токен в URL, получатель и текст — в теле: контракт Bot API.
    assert calls[0]["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert calls[0]["data"] == {"chat_id": CHAT_ID, "text": "Привет!"}


def test_send_api_error(client, tutor_factory, monkeypatch):
    calls = []
    _patch_urlopen(
        monkeypatch,
        lambda call: _FakeResponse({"ok": False, "description": "Unauthorized"}),
        calls,
    )
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect(db, tutor_id)
        errors = send_message(db, tutor_id, "telegram", CHAT_ID, "привет")

    assert errors and "Unauthorized" in errors[0]
    # RetrySender делает 3 попытки, прежде чем сдаться.
    assert len(calls) == 3


def test_send_http_error_uses_api_description(client, tutor_factory, monkeypatch):
    """HTTP 4xx: описание ошибки берётся из тела ответа Telegram."""

    def fail(call):
        raise urllib.error.HTTPError(
            call["url"], 404, "Not Found", None,
            io.BytesIO(b'{"ok": false, "description": "chat not found"}'),
        )

    calls = []
    _patch_urlopen(monkeypatch, fail, calls)
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect(db, tutor_id)
        errors = send_message(db, tutor_id, "telegram", CHAT_ID, "привет")

    assert errors and "chat not found" in errors[0]


# ---------------------------------------------------------------------------
# send_message: MAX (HTTP подменён)
# ---------------------------------------------------------------------------


def _connect_max(db, tutor_id, token=MAX_TOKEN):
    set_param(db, tutor_id, token_key("max"), token)


def test_send_max_success(client, tutor_factory, monkeypatch):
    calls = []
    _patch_urlopen(
        monkeypatch,
        lambda call: _FakeResponse({"message": {"body": {"text": "Привет!"}}}),
        calls,
    )
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect_max(db, tutor_id)
        errors = send_message(db, tutor_id, "max", CHAT_ID, "Привет!")

    assert errors == []
    assert len(calls) == 1
    # chat_id — в query, токен — сырой строкой в Authorization (без Bearer),
    # текст — в JSON-теле: контракт Bot API MAX.
    assert calls[0]["url"] == (
        f"https://platform-api2.max.ru/messages?chat_id={CHAT_ID}"
    )
    assert calls[0]["headers"]["Authorization"] == MAX_TOKEN
    assert calls[0]["data"] == {"text": "Привет!"}


def test_send_max_api_error(client, tutor_factory, monkeypatch):
    """HTTP 4xx/5xx с телом «{code, message}»: показываем message."""

    def fail(call):
        raise urllib.error.HTTPError(
            call["url"], 404, "Not Found", None,
            io.BytesIO('{"code": "chat.not.found", "message": "Чат не найден"}'.encode()),
        )

    calls = []
    _patch_urlopen(monkeypatch, fail, calls)
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect_max(db, tutor_id)
        errors = send_message(db, tutor_id, "max", CHAT_ID, "привет")

    assert errors and "Чат не найден" in errors[0]
    # RetrySender делает 3 попытки, прежде чем сдаться.
    assert len(calls) == 3


def test_send_max_unexpected_response(client, tutor_factory, monkeypatch):
    """200 без объекта сообщения — тоже ошибка доставки."""

    calls = []
    _patch_urlopen(monkeypatch, lambda call: _FakeResponse({"unknown": 1}), calls)
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect_max(db, tutor_id)
        errors = send_message(db, tutor_id, "max", CHAT_ID, "привет")

    assert errors and "неожиданный ответ" in errors[0]


@pytest.mark.parametrize(
    "messenger",
    [
        pytest.param("telegram", id="telegram"),
        pytest.param("max", id="max"),
    ],
)
def test_send_network_error(messenger, client, tutor_factory, monkeypatch):
    """Недоступная сеть — ошибка доставки у любого мессенджера."""

    def fail(call):
        raise urllib.error.URLError("connection refused")

    calls = []
    _patch_urlopen(monkeypatch, fail, calls)
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        set_param(db, tutor_id, token_key(messenger), TOKEN)
        errors = send_message(db, tutor_id, messenger, CHAT_ID, "привет")

    assert errors and "сеть недоступна" in errors[0]

def test_connected_messengers_orders_by_closed_list(client, tutor_factory):
    """Подключены оба: порядок задаёт MESSENGERS, а не порядок сохранения."""
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect_max(db, tutor_id)
        _connect(db, tutor_id)
        assert connected_messengers(db, tutor_id) == ["telegram", "max"]


# ---------------------------------------------------------------------------
# Декораторы-обёртки
# ---------------------------------------------------------------------------


class _FlakySender:
    """Заглушка: падает первые `failures` раз, потом доставляет."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def send(self, config, recipient, text):
        self.calls += 1
        if self.calls <= self.failures:
            raise SendError("бум")


def test_retry_sender_succeeds_after_failure():
    inner = _FlakySender(failures=1)
    RetrySender(inner, attempts=3).send("token", "chat", "text")
    assert inner.calls == 2


def test_retry_sender_raises_after_exhausting_attempts():
    inner = _FlakySender(failures=10)
    with pytest.raises(SendError):
        RetrySender(inner, attempts=3).send("token", "chat", "text")
    assert inner.calls == 3


def test_logging_sender_passes_success():
    inner = _FlakySender(failures=0)
    LoggingSender(inner, messenger="Telegram").send("token", "chat", "text")
    assert inner.calls == 1


def test_logging_sender_reraises_failure():
    inner = _FlakySender(failures=1)
    with pytest.raises(SendError):
        LoggingSender(inner, messenger="Telegram").send("token", "chat", "text")
