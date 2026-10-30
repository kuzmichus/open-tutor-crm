"""Тесты блока «Каналы уведомлений»: привязка мессенджеров по диплинку.

Поведение через HTTP тем же путём, что у пользователя: те же маршруты,
htmx-фрагменты ищутся по разметке. HTTP-транспорт подменяется
(monkeypatch на `urllib.request.urlopen`) — сеть в тестах не дёргается,
но путь вызова тот же, что в бою.
"""

import json
import urllib.error
import urllib.request
from io import BytesIO

from sqlalchemy import text

from app.config import settings as app_settings
from app.database import SessionLocal
from app.messenger.services.binding import (
    bind_code_key,
    bind_link_key,
    chat_id_key,
    chat_label_key,
    marker_key,
)
from app.messenger.services.messengers import token_key
from app.tutor.services.params import delete_param, get_param, set_param

PASSWORD = "Секретный-Пароль-1"
TELEGRAM_TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
MAX_TOKEN = "pKcfaXfFUnfTSMPSYJjpdHHnPEMucRQGxFYEXhIq"

HTMX = {"HX-Request": "true"}

CHECK_URL = "/tutor/profile/notifications/channels"
TAB_URL = "/tutor/profile?tab=notifications"


# ---------------------------------------------------------------------------
# Вспомогательное: вход, транспорт, параметры
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Минимальный ответ urlopen: context manager с JSON-телом."""

    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _api_error(description):
    """HTTPError с телом в формате API (для проверки текста ошибки)."""
    return urllib.error.HTTPError(
        "https://api.example.test",
        401,
        "Unauthorized",
        None,
        BytesIO(json.dumps({"description": description}).encode()),
    )


def _patch_urlopen(monkeypatch, responder, calls):
    """Подменяет urlopen; каждый вызов (URL + заголовки + тело + TLS) — в `calls`."""

    def fake_urlopen(request, timeout=None, context=None):
        raw = request.data
        calls.append({
            "url": request.full_url,
            "headers": {
                name.lower(): value
                for name, value in request.header_items()
            },
            # Тело POST (sendMessage, POST /messages) — словарь; у GET его нет.
            "data": json.loads(raw.decode()) if raw else None,
            # verify_mode: 2 = CERT_REQUIRED (проверка), 0 = CERT_NONE.
            "tls_verify": context is None or context.verify_mode != 0,
        })
        return responder(calls[-1]["url"])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _telegram_routes(routes):
    """Маршрутизатор ответов по подстроке URL; значение — payload,
    исключение или фабрика исключения (свежее на каждую попытку: ретрай
    перечитывает тело HTTPError, одноразовый BytesIO на второй попытке
    пуст). Один фейк обслуживает и Telegram, и MAX."""

    def responder(url):
        for fragment, answer in routes.items():
            if fragment in url:
                if callable(answer) and not isinstance(answer, Exception):
                    answer = answer()
                if isinstance(answer, Exception):
                    raise answer
                return _FakeResponse(answer)
        raise AssertionError(f"нет заглушки для {url}")

    return responder


def _register_and_login(client, email):
    client.post(
        "/tutor/register",
        data={
            "name": "Каналы Уведомлений",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )


def _tutor_id(client, email):
    with SessionLocal() as db:
        return db.execute(
            text("select id from tutors where email = :e"), {"e": email}
        ).scalar()


def _param(tutor_id, key):
    with SessionLocal() as db:
        return get_param(db, tutor_id, key)


def _connect_token(tutor_id, messenger, token):
    with SessionLocal() as db:
        set_param(db, tutor_id, token_key(messenger), token)


def _set_param(tutor_id, key, value):
    with SessionLocal() as db:
        set_param(db, tutor_id, key, value)


# ---------------------------------------------------------------------------
# Доступ и блок на вкладке
# ---------------------------------------------------------------------------


def test_check_url_redirects_to_login_without_session(client):
    response = client.get(CHECK_URL, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_connect_url_redirects_to_login_without_session(client):
    response = client.post(
        f"{CHECK_URL}/telegram/connect", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_tab_shows_channels_block(client):
    _register_and_login(client, "channels-tab@example.com")
    html = client.get(TAB_URL).text
    assert "Каналы уведомлений" in html
    assert "Уведомления в Telegram" in html
    assert "Уведомления в MAX" in html
    assert html.count("Подключить") == 2


def test_tab_has_no_bind_polling_while_idle(client):
    """Без незавершённой привязки автоопрос не включается."""
    _register_and_login(client, "channels-idle@example.com")
    html = client.get(TAB_URL).text
    assert 'hx-trigger="every 4s"' not in html


# ---------------------------------------------------------------------------
# Подключение: генерация ссылки
# ---------------------------------------------------------------------------


def test_connect_without_token_shows_hint(client):
    _register_and_login(client, "channels-notoken@example.com")
    response = client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)
    assert response.status_code == 200
    assert "вставьте его токен" in response.text
    assert "channels-block" in response.text


def test_connect_without_token_saves_nothing(client):
    _register_and_login(client, "channels-notoken2@example.com")
    tutor_id = _tutor_id(client, "channels-notoken2@example.com")
    client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)
    assert _param(tutor_id, bind_code_key("telegram")) is None


def test_connect_without_token_no_js_redirects_with_hint(client):
    _register_and_login(client, "channels-nojs@example.com")
    response = client.post(f"{CHECK_URL}/telegram/connect", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"{TAB_URL}&bind_error=1"
    # Бrowser следует редиректу — общий hint приходит параметром.
    html = client.get(response.headers["location"]).text
    assert "Не удалось начать привязку" in html


def test_connect_builds_telegram_link(client, monkeypatch):
    email = "channels-tg@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _connect_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    calls = []
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}}),
        calls,
    )

    response = client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)

    assert response.status_code == 200
    assert "https://t.me/tutor_bot?start=" in response.text
    code = _param(tutor_id, bind_code_key("telegram"))
    assert code and code in _param(tutor_id, bind_link_key("telegram"))
    assert len(calls) == 1


def test_connect_reports_bot_api_error(client, monkeypatch):
    email = "channels-tgerr@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _connect_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({"/getMe": _api_error("Unauthorized")}),
        [],
    )

    response = client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)

    assert "Telegram: Unauthorized" in response.text
    assert _param(tutor_id, bind_code_key("telegram")) is None


def test_connect_reports_network_error(client, monkeypatch):
    email = "channels-tgnet@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _connect_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({"/getMe": urllib.error.URLError("Connection refused")}),
        [],
    )

    response = client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)

    assert "сеть недоступна" in response.text
    assert _param(tutor_id, bind_code_key("telegram")) is None


def test_connect_max_builds_link(client, monkeypatch):
    email = "channels-max@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _connect_token(tutor_id, "max", MAX_TOKEN)
    calls = []
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/me": {"user_id": 7, "name": "Bot", "username": "maxbot"},
            "/updates": {"updates": [], "marker": 55},
        }),
        calls,
    )

    response = client.post(f"{CHECK_URL}/max/connect", headers=HTMX)

    assert "https://max.ru/maxbot?start=" in response.text
    # Контракт MAX: токен сырой строкой в Authorization, без Bearer.
    assert MAX_TOKEN in str(calls)
    assert "Bearer" not in str(calls)


def test_connect_unknown_messenger_404(client):
    _register_and_login(client, "channels-404@example.com")
    assert client.post(f"{CHECK_URL}/vk/connect", headers=HTMX).status_code == 404
    assert client.post(f"{CHECK_URL}/vk/unlink", headers=HTMX).status_code == 404


# ---------------------------------------------------------------------------
# Подтверждение привязки по апдейтам
# ---------------------------------------------------------------------------


def _start_binding(client, tutor_id, monkeypatch, routes):
    """Готовит привязку Telegram и возвращает сохранённый код."""
    _connect_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(monkeypatch, _telegram_routes(routes), [])
    client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)
    code = _param(tutor_id, bind_code_key("telegram"))
    assert code
    return code


def test_confirm_binds_chat_by_start_code(client, monkeypatch):
    email = "channels-confirm@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    code = _start_binding(client, tutor_id, monkeypatch, {"/getMe": {"ok": True, "result": {"username": "tutor_bot"}}})
    calls = []
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/getUpdates": {
                "ok": True,
                "result": [{
                    "update_id": 10,
                    "message": {
                        "text": f"/start {code}",
                        "chat": {"id": 100200300, "username": "kuzmichus"},
                        "from": {"username": "kuzmichus"},
                    },
                }],
            },
            "/sendMessage": {"ok": True, "result": {"message_id": 1}},
        }),
        calls,
    )

    response = client.get(CHECK_URL, headers=HTMX)

    assert "Telegram подключен" in response.text
    assert "@kuzmichus" in response.text
    assert _param(tutor_id, chat_id_key("telegram")) == "100200300"
    assert _param(tutor_id, chat_label_key("telegram")) == "@kuzmichus"
    assert _param(tutor_id, bind_code_key("telegram")) is None
    # После привязки бот приветствует чат: chat_id и текст — в sendMessage.
    welcome = calls[-1]
    assert "/sendMessage" in welcome["url"]
    assert welcome["data"]["chat_id"] == "100200300"
    assert "подключён" in welcome["data"]["text"]


def test_confirm_binds_chat_by_label_fallback(client, monkeypatch):
    """Чат без username подписывается именем."""
    email = "channels-fallback@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    code = _start_binding(client, tutor_id, monkeypatch, {"/getMe": {"ok": True, "result": {"username": "tutor_bot"}}})
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/getUpdates": {
                "ok": True,
                "result": [{
                    "update_id": 11,
                    "message": {
                        "text": f"/start {code}",
                        "chat": {"id": 55, "first_name": "Анна"},
                    },
                }],
            },
            "/sendMessage": {"ok": True, "result": {"message_id": 1}},
        }),
        [],
    )

    client.get(CHECK_URL, headers=HTMX)

    assert _param(tutor_id, chat_label_key("telegram")) == "Анна"


def test_check_without_start_stays_pending(client, monkeypatch):
    email = "channels-pending@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    code = _start_binding(client, tutor_id, monkeypatch, {"/getMe": {"ok": True, "result": {"username": "tutor_bot"}}})
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/getUpdates": {
                "ok": True,
                "result": [{"update_id": 12, "message": {"text": "/start", "chat": {"id": 1}}}],
            }
        }),
        [],
    )

    response = client.get(CHECK_URL, headers=HTMX)

    assert "Перейдите в чат с ботом" in response.text
    # Пока привязка не завершена, фрагмент опрашивает сам себя.
    assert 'hx-trigger="every 4s"' in response.text
    assert _param(tutor_id, chat_id_key("telegram")) is None
    assert _param(tutor_id, bind_code_key("telegram")) == code


def test_check_with_foreign_code_stays_pending(client, monkeypatch):
    email = "channels-foreign@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _start_binding(client, tutor_id, monkeypatch, {"/getMe": {"ok": True, "result": {"username": "tutor_bot"}}})
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/getUpdates": {
                "ok": True,
                "result": [{
                    "update_id": 13,
                    "message": {"text": "/start чужой-код", "chat": {"id": 99}},
                }],
            }
        }),
        [],
    )

    client.get(CHECK_URL, headers=HTMX)

    assert _param(tutor_id, chat_id_key("telegram")) is None


def test_check_without_binding_calls_nothing(client, monkeypatch):
    _register_and_login(client, "channels-check@example.com")
    calls = []
    _patch_urlopen(monkeypatch, _telegram_routes({"/getMe": {"ok": True, "result": {}}}), calls)

    client.get(CHECK_URL, headers=HTMX)

    assert calls == []


def test_check_no_js_renders_full_page(client):
    """Ручная «Проверить» без htmx — целая страница, не фрагмент."""
    _register_and_login(client, "channels-fullpage@example.com")
    response = client.get(CHECK_URL)
    assert response.status_code == 200
    assert "<html" in response.text
    assert "Каналы уведомлений" in response.text


# ---------------------------------------------------------------------------
# MAX: bot_started с payload
# ---------------------------------------------------------------------------


def _start_max_binding(client, tutor_id, monkeypatch):
    _connect_token(tutor_id, "max", MAX_TOKEN)
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/me": {"user_id": 7, "name": "Bot", "username": "maxbot"},
            # Снапшот головы потока при создании кода.
            "/updates": {"updates": [], "marker": 55},
        }),
        [],
    )
    client.post(f"{CHECK_URL}/max/connect", headers=HTMX)
    code = _param(tutor_id, bind_code_key("max"))
    assert code
    return code


def test_connect_max_snapshots_stream_marker(client, monkeypatch):
    """Подключение фиксирует голову потока апдейтов: без маркера MAX отдаёт
    только последнее обновление, и первая проверка могла бы его пропустить."""
    email = "channels-maxsnapshot@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _connect_token(tutor_id, "max", MAX_TOKEN)
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/me": {"user_id": 7, "name": "Bot", "username": "maxbot"},
            "/updates": {"updates": [], "marker": 77},
        }),
        [],
    )

    client.post(f"{CHECK_URL}/max/connect", headers=HTMX)

    assert _param(tutor_id, marker_key("max")) == "77"


def test_confirm_max_binds_chat_by_payload(client, monkeypatch):
    """Схема апдейта плоская: payload, chat_id и user — на верхнем уровне."""
    email = "channels-maxconfirm@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    code = _start_max_binding(client, tutor_id, monkeypatch)
    calls = []
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/updates": {
                "updates": [{
                    "update_type": "bot_started",
                    "timestamp": 0,
                    "payload": code,
                    "chat_id": 4242,
                    "user": {"user_id": 101, "name": "Ольга", "username": "olga"},
                    "user_locale": "ru",
                }],
                "marker": 56,
            },
            "/messages": {"message": {"text": "ok"}},
        }),
        calls,
    )

    response = client.get(CHECK_URL, headers=HTMX)

    assert "MAX подключен" in response.text
    assert "@olga" in response.text
    assert _param(tutor_id, chat_id_key("max")) == "4242"
    assert _param(tutor_id, marker_key("max")) == "56"
    assert _param(tutor_id, bind_code_key("max")) is None


def test_confirm_max_reads_updates_by_saved_marker(client, monkeypatch):
    """Проверки читают апдейты от сохранённого маркера (снапшот при
    подключении зафиксировал голову потока)."""
    email = "channels-maxmarker@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _start_max_binding(client, tutor_id, monkeypatch)
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({"/updates": {"updates": [], "marker": 55}}),
        [],
    )
    client.get(CHECK_URL, headers=HTMX)

    calls = []
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({"/updates": {"updates": [], "marker": 55}}),
        calls,
    )
    client.get(CHECK_URL, headers=HTMX)

    assert "marker=55" in calls[0]["url"]


def test_confirm_max_falls_back_to_user_id(client, monkeypatch):
    email = "channels-maxuid@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    code = _start_max_binding(client, tutor_id, monkeypatch)
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/updates": {
                "updates": [{
                    "update_type": "bot_started",
                    "payload": code,
                    "user": {"user_id": 303, "name": "Пётр"},
                }],
                "marker": 56,
            },
            "/messages": {"message": {"text": "ok"}},
        }),
        [],
    )

    client.get(CHECK_URL, headers=HTMX)

    assert _param(tutor_id, chat_id_key("max")) == "303"
    assert _param(tutor_id, chat_label_key("max")) == "Пётр"


def test_confirm_max_without_marker_keeps_unread_updates(client, monkeypatch):
    """Чтение без маркера, вернувшее непустой список без нашего кода,
    ничего не потребляет: впереди могли остаться непросмотренные апдейты."""
    email = "channels-maxkeep@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _start_max_binding(client, tutor_id, monkeypatch)
    with SessionLocal() as db:
        delete_param(db, tutor_id, marker_key("max"))
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/updates": {
                "updates": [{
                    "update_type": "message_created",
                    "payload": {"message": {"text": "привет"}},
                }],
                "marker": 60,
            },
        }),
        [],
    )

    client.get(CHECK_URL, headers=HTMX)

    assert _param(tutor_id, marker_key("max")) is None
    assert _param(tutor_id, bind_code_key("max")) is not None


def test_confirm_max_without_marker_saves_head_on_empty_stream(client, monkeypatch):
    """Пустой поток без маркера безопасен: просмотрено всё, голову
    сохраняем — следующие проверки идут инкрементально от неё."""
    email = "channels-maxhead@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _start_max_binding(client, tutor_id, monkeypatch)
    with SessionLocal() as db:
        delete_param(db, tutor_id, marker_key("max"))
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({"/updates": {"updates": [], "marker": 61}}),
        [],
    )

    client.get(CHECK_URL, headers=HTMX)

    assert _param(tutor_id, marker_key("max")) == "61"


# ---------------------------------------------------------------------------
# Отвязка и изоляция
# ---------------------------------------------------------------------------


def _bind_telegram(client, tutor_id, monkeypatch):
    code = _start_binding(client, tutor_id, monkeypatch, {"/getMe": {"ok": True, "result": {"username": "tutor_bot"}}})
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/getUpdates": {
                "ok": True,
                "result": [{
                    "update_id": 14,
                    "message": {"text": f"/start {code}", "chat": {"id": 777, "username": "bound"}},
                }],
            },
            "/sendMessage": {"ok": True, "result": {"message_id": 1}},
        }),
        [],
    )
    client.get(CHECK_URL, headers=HTMX)
    assert _param(tutor_id, chat_id_key("telegram")) == "777"


def test_unlink_removes_chat_keeps_token(client, monkeypatch):
    email = "channels-unlink@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _bind_telegram(client, tutor_id, monkeypatch)

    response = client.post(f"{CHECK_URL}/telegram/unlink", headers=HTMX)

    assert "Уведомления в Telegram" in response.text
    assert _param(tutor_id, chat_id_key("telegram")) is None
    assert _param(tutor_id, chat_label_key("telegram")) is None
    assert _param(tutor_id, token_key("telegram")) == TELEGRAM_TOKEN


def test_unlink_no_js_redirects(client, monkeypatch):
    email = "channels-unlink2@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _bind_telegram(client, tutor_id, monkeypatch)

    response = client.post(
        f"{CHECK_URL}/telegram/unlink", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == TAB_URL
    assert _param(tutor_id, chat_id_key("telegram")) is None


def test_reconnect_replaces_code_and_link(client, monkeypatch):
    email = "channels-reconnect@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _connect_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({"/getMe": {"ok": True, "result": {"username": "tutor_bot"}}}),
        [],
    )
    client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)
    old_code = _param(tutor_id, bind_code_key("telegram"))
    client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)

    assert _param(tutor_id, bind_code_key("telegram")) != old_code


def test_channels_isolated_by_tutor(client, monkeypatch):
    """Привязка репетитора A не видна и не влияет на репетитора B."""
    email_a = "channels-a@example.com"
    email_b = "channels-b@example.com"
    _register_and_login(client, email_a)
    tutor_a = _tutor_id(client, email_a)
    _bind_telegram(client, tutor_a, monkeypatch)

    _register_and_login(client, email_b)
    tutor_b = _tutor_id(client, email_b)
    html = client.get(TAB_URL).text

    assert "Telegram подключен" not in html
    assert html.count("Подключить") == 2
    assert _param(tutor_a, chat_id_key("telegram")) == "777"
    assert _param(tutor_b, chat_id_key("telegram")) is None


def test_pending_without_token_falls_back_to_idle(client):
    """Токен удалён при незавершённой привязке — карточка не зависает
    «в процессе», поллинг не включается."""
    email = "channels-stale@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _set_param(tutor_id, bind_link_key("telegram"), "https://t.me/bot?start=code")
    _set_param(tutor_id, bind_code_key("telegram"), "code")

    html = client.get(TAB_URL).text

    assert "Открыть Telegram" not in html
    assert 'hx-trigger="every 4s"' not in html
    assert "Подключить" in html


# ---------------------------------------------------------------------------
# TLS: флаг проверки сертификатов API мессенджеров
# ---------------------------------------------------------------------------


def test_tls_verification_when_setting_on(client, monkeypatch):
    """Флаг включён — сертификат сервера проверяется (CERT_REQUIRED)."""
    email = "channels-tls-on@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _connect_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    monkeypatch.setattr(app_settings, "messenger_tls_verify", True)
    calls = []
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({"/getMe": {"ok": True, "result": {"username": "tutor_bot"}}}),
        calls,
    )

    client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)

    assert calls[0]["tls_verify"] is True


def test_tls_verification_can_be_disabled(client, monkeypatch):
    """Сертификат MAX подписан корнем Минцифры: флаг окружения отключает
    проверку подлинности сервера (канал остаётся зашифрованным)."""
    email = "channels-tls-off@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    _connect_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    monkeypatch.setattr(app_settings, "messenger_tls_verify", False)
    calls = []
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({"/getMe": {"ok": True, "result": {"username": "tutor_bot"}}}),
        calls,
    )

    client.post(f"{CHECK_URL}/telegram/connect", headers=HTMX)

    assert calls[0]["tls_verify"] is False


# ---------------------------------------------------------------------------
# Приветственное сообщение после привязки
# ---------------------------------------------------------------------------


def test_welcome_sent_to_max_chat_after_binding(client, monkeypatch):
    email = "channels-welcomemax@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    code = _start_max_binding(client, tutor_id, monkeypatch)
    calls = []
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/updates": {
                "updates": [{
                    "update_type": "bot_started",
                    "payload": code,
                    "chat_id": 4242,
                    "user": {"user_id": 101, "username": "olga"},
                }],
                "marker": 57,
            },
            "/messages": {"message": {"text": "ok"}},
        }),
        calls,
    )

    client.get(CHECK_URL, headers=HTMX)

    welcome = calls[-1]
    assert "/messages" in welcome["url"]
    assert "chat_id=4242" in welcome["url"]
    assert "подключён" in welcome["data"]["text"]


def test_welcome_failure_does_not_break_binding(client, monkeypatch):
    """Сбой приветствия не отменяет привязку: чат остаётся подключён,
    ошибка показывается в блоке."""
    email = "channels-welcomefail@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    code = _start_binding(client, tutor_id, monkeypatch, {"/getMe": {"ok": True, "result": {"username": "tutor_bot"}}})
    _patch_urlopen(
        monkeypatch,
        _telegram_routes({
            "/getUpdates": {
                "ok": True,
                "result": [{
                    "update_id": 15,
                    "message": {"text": f"/start {code}", "chat": {"id": 888, "username": "bound"}},
                }],
            },
            "/sendMessage": lambda: _api_error("Forbidden: bot was blocked by the user"),
        }),
        [],
    )

    response = client.get(CHECK_URL, headers=HTMX)

    assert "Telegram подключен" in response.text
    assert _param(tutor_id, chat_id_key("telegram")) == "888"
    assert "Forbidden" in response.text
