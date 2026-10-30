"""Тесты блока «Приглашение в мессенджеры» в карточке ученика.

Поведение через HTTP тем же путём, что у пользователя: те же маршруты,
htmx-фрагменты ищутся по разметке. HTTP-транспорт подменяется
(monkeypatch на `urllib.request.urlopen`) — сеть в тестах не дёргается,
но путь вызова тот же, что в бою.
"""

import json
import urllib.error
import urllib.request
from io import BytesIO

from sqlalchemy import select, text

from app.database import SessionLocal
from app.messenger.models.student_invite import StudentMessengerInvite
from app.messenger.services.binding import (
    bind_code_key,
    chat_id_key,
    marker_key,
)
from app.messenger.services.messengers import token_key
from app.tutor.services.params import get_param, set_param

PASSWORD = "Секретный-Пароль-1"
TELEGRAM_TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
MAX_TOKEN = "pKcfaXfFUnfTSMPSYJjpdHHnPEMucRQGxFYEXhIq"

HTMX = {"HX-Request": "true"}


# ---------------------------------------------------------------------------
# Вспомогательное: вход, ученики, транспорт, параметры
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


def _patch_urlopen(monkeypatch, routes):
    """Подменяет urlopen; ответ выбирается по подстроке URL.
    Значение — payload, исключение или фабрика исключения."""

    def fake_urlopen(request, timeout=None, context=None):
        url = request.full_url
        for fragment, answer in routes.items():
            if fragment in url:
                if callable(answer) and not isinstance(answer, Exception):
                    answer = answer()
                if isinstance(answer, Exception):
                    raise answer
                return _FakeResponse(answer)
        raise AssertionError(f"нет заглушки для {url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _register_and_login(client, email):
    client.post(
        "/tutor/register",
        data={
            "name": "Приглашения Учеников",
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


def _create_student(client, first_name):
    """Ученик создаётся тем же POST-маршрутом, что и у пользователя."""
    client.post("/tutor/students", data={"first_name": first_name})
    with SessionLocal() as db:
        return db.execute(
            text(
                "select id from students where first_name = :n "
                "order by created_at desc limit 1"
            ),
            {"n": first_name},
        ).scalar()


def _student_id(client, email, first_name):
    with SessionLocal() as db:
        tutor_id = db.execute(
            text("select id from tutors where email = :e"), {"e": email}
        ).scalar()
        return db.execute(
            text(
                "select id from students where tutor_id = :t and first_name = :n"
            ),
            {"t": tutor_id, "n": first_name},
        ).scalar()


def _invite_row(student_id, messenger):
    with SessionLocal() as db:
        return db.scalar(
            select(StudentMessengerInvite).where(
                StudentMessengerInvite.student_id == student_id,
                StudentMessengerInvite.messenger == messenger,
            )
        )


def _invite_fields(student_id, messenger):
    row = _invite_row(student_id, messenger)
    if row is None:
        return None
    return (row.invite_code, row.invite_link, row.chat_id, row.chat_label)


def _set_token(tutor_id, messenger, token):
    with SessionLocal() as db:
        set_param(db, tutor_id, token_key(messenger), token)


def _param(tutor_id, key):
    with SessionLocal() as db:
        return get_param(db, tutor_id, key)


def _tutor_id(client, email):
    with SessionLocal() as db:
        return db.execute(
            text("select id from tutors where email = :e"), {"e": email}
        ).scalar()


def _fragment_url(student_id):
    return f"/tutor/students/{student_id}/messengers"


# ---------------------------------------------------------------------------
# Доступ и блок на вкладке
# ---------------------------------------------------------------------------


def test_invites_url_redirects_to_login_without_session(client):
    response = client.get("/tutor/students/whatever/messengers", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    response = client.post(
        "/tutor/students/whatever/messengers/telegram/invite",
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_settings_tab_shows_invites_block(client):
    email = "invites-tab@example.com"
    _register_and_login(client, email)
    student_id = _create_student(client, "Ольга")
    html = client.get(f"/tutor/students/{student_id}/edit", headers=HTMX).text
    assert "Приглашение в мессенджеры" in html
    assert html.count("Пригласить") == 2
    # Без непогашенного приглашения автоопрос не включается.
    assert 'hx-trigger="every 4s"' not in html


def test_new_student_form_has_no_invites_block(client):
    _register_and_login(client, "invites-new@example.com")
    html = client.get("/tutor/students/new", headers=HTMX).text
    assert "Приглашение в мессенджеры" not in html


# ---------------------------------------------------------------------------
# Генерация ссылки приглашения
# ---------------------------------------------------------------------------


def test_invite_without_token_shows_hint(client):
    email = "invites-notoken@example.com"
    _register_and_login(client, email)
    student_id = _create_student(client, "Ольга")
    response = client.post(
        f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX
    )
    assert response.status_code == 200
    assert "вставьте его токен" in response.text
    assert _invite_row(student_id, "telegram") is None


def test_invite_builds_telegram_link(client, monkeypatch):
    email = "invites-tg@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}},
    )

    response = client.post(
        f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX
    )

    assert response.status_code == 200
    assert "https://t.me/tutor_bot?start=" in response.text
    # Ссылка дублируется открытым текстом — её видно целиком.
    assert "Отправьте ученику эту ссылку" in response.text
    # Ответ «Пригласить» включает автокопирование и поллинг.
    assert 'data-autocopy="telegram"' in response.text
    assert 'hx-trigger="every 4s"' in response.text
    code, link, chat_id, _label = _invite_fields(student_id, "telegram")
    assert code and code in link and chat_id is None


def test_invite_reports_bot_api_error(client, monkeypatch):
    email = "invites-tgerr@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(monkeypatch, {"/getMe": _api_error("Unauthorized")})

    response = client.post(
        f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX
    )

    assert "Telegram: Unauthorized" in response.text
    assert _invite_row(student_id, "telegram") is None


def test_invite_unknown_messenger_404(client):
    email = "invites-404@example.com"
    _register_and_login(client, email)
    student_id = _create_student(client, "Ольга")
    assert client.post(
        f"{_fragment_url(student_id)}/vk/invite", headers=HTMX
    ).status_code == 404
    assert client.post(
        f"{_fragment_url(student_id)}/vk/unlink", headers=HTMX
    ).status_code == 404


def test_invite_no_js_redirects_to_student_page(client, monkeypatch):
    email = "invites-nojs@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}},
    )

    response = client.post(
        f"{_fragment_url(student_id)}/telegram/invite", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tutor/students/{student_id}"


def test_reinvite_replaces_code_and_link(client, monkeypatch):
    email = "invites-reinvite@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}},
    )
    client.post(f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX)
    old = _invite_fields(student_id, "telegram")
    client.post(f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX)

    new = _invite_fields(student_id, "telegram")
    assert new[0] != old[0]
    assert new[1] != old[1]


# ---------------------------------------------------------------------------
# Подтверждение по апдейтам
# ---------------------------------------------------------------------------


def test_confirm_binds_student_by_start_code(client, monkeypatch):
    email = "invites-confirm@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}},
    )
    client.post(f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX)
    code = _invite_fields(student_id, "telegram")[0]
    assert code
    _patch_urlopen(
        monkeypatch,
        {
            "/getUpdates": {
                "ok": True,
                "result": [{
                    "update_id": 10,
                    "message": {
                        "text": f"/start {code}",
                        "chat": {"id": 100200300, "username": "olga_student"},
                    },
                }],
            },
            "/sendMessage": {"ok": True, "result": {"message_id": 1}},
        },
    )

    response = client.get(_fragment_url(student_id), headers=HTMX)

    assert "Ученик подключён к Telegram" in response.text
    assert "@olga_student" in response.text
    # Привязка погашает приглашение: кода и ссылки больше нет.
    code, link, chat_id, label = _invite_fields(student_id, "telegram")
    assert chat_id == "100200300"
    assert label == "@olga_student"
    assert code is None and link is None
    # После привязки бот приветствует чат ученика.
    # После привязки автоопрос выключается.
    assert 'hx-trigger="every 4s"' not in response.text


def test_confirm_max_binds_student_by_payload(client, monkeypatch):
    email = "invites-max@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "max", MAX_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {
            "/me": {"user_id": 7, "name": "Bot", "username": "maxbot"},
            "/updates": {"updates": [], "marker": 55},
        },
    )
    client.post(f"{_fragment_url(student_id)}/max/invite", headers=HTMX)
    code = _invite_fields(student_id, "max")[0]
    assert code
    _patch_urlopen(
        monkeypatch,
        {
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
        },
    )

    response = client.get(_fragment_url(student_id), headers=HTMX)

    assert "Ученик подключён к MAX" in response.text
    assert "@olga" in response.text
    _code, _link, chat_id, label = _invite_fields(student_id, "max")
    assert chat_id == "4242"
    assert label == "@olga"
    # Маркер общий и двигается проверкой.
    assert _param(tutor_id, marker_key("max")) == "56"


def test_start_without_known_code_stays_pending(client, monkeypatch):
    email = "invites-foreign@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}},
    )
    client.post(f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX)
    code = _invite_fields(student_id, "telegram")[0]
    _patch_urlopen(
        monkeypatch,
        {
            "/getUpdates": {
                "ok": True,
                "result": [{
                    "update_id": 12,
                    "message": {"text": "/start чужой-код", "chat": {"id": 99}},
                }],
            }
        },
    )

    response = client.get(_fragment_url(student_id), headers=HTMX)

    assert "Отправьте ученику эту ссылку" in response.text
    assert 'hx-trigger="every 4s"' in response.text
    assert _invite_fields(student_id, "telegram")[0] == code


def test_confirm_binds_channel_and_student_in_one_pass(client, monkeypatch):
    """Коды канала и приглашения привязываются за одно чтение апдейтов."""
    email = "invites-both@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}},
    )
    # Незавершённая привязка канала репетитора.
    client.post(
        "/tutor/profile/notifications/channels/telegram/connect", headers=HTMX
    )
    channel_code = _param(tutor_id, bind_code_key("telegram"))
    assert channel_code
    # Незавершённое приглашение ученика.
    client.post(f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX)
    invite_code = _invite_fields(student_id, "telegram")[0]
    assert invite_code
    _patch_urlopen(
        monkeypatch,
        {
            "/getUpdates": {
                "ok": True,
                "result": [
                    {
                        "update_id": 20,
                        "message": {
                            "text": f"/start {channel_code}",
                            "chat": {"id": 777, "username": "tutor_chat"},
                        },
                    },
                    {
                        "update_id": 21,
                        "message": {
                            "text": f"/start {invite_code}",
                            "chat": {"id": 888, "username": "olga_student"},
                        },
                    },
                ],
            },
            "/sendMessage": {"ok": True, "result": {"message_id": 1}},
        },
    )

    response = client.get(_fragment_url(student_id), headers=HTMX)

    assert "Ученик подключён к Telegram" in response.text
    assert _invite_fields(student_id, "telegram")[2] == "888"
    assert _param(tutor_id, chat_id_key("telegram")) == "777"
    assert _param(tutor_id, bind_code_key("telegram")) is None


# ---------------------------------------------------------------------------
# Отвязка и изоляция
# ---------------------------------------------------------------------------


def test_unbind_removes_invite_and_chat(client, monkeypatch):
    email = "invites-unlink@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}},
    )
    client.post(f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX)
    code = _invite_fields(student_id, "telegram")[0]
    _patch_urlopen(
        monkeypatch,
        {
            "/getUpdates": {
                "ok": True,
                "result": [{
                    "update_id": 14,
                    "message": {
                        "text": f"/start {code}",
                        "chat": {"id": 555, "username": "olga_student"},
                    },
                }],
            },
            "/sendMessage": {"ok": True, "result": {"message_id": 1}},
        },
    )
    client.get(_fragment_url(student_id), headers=HTMX)
    assert _invite_fields(student_id, "telegram")[2] == "555"

    response = client.post(
        f"{_fragment_url(student_id)}/telegram/unlink", headers=HTMX
    )

    # Telegram вернулся в «не приглашён», MAX остался соседней карточкой.
    assert "Приглашение в Telegram" in response.text
    assert "Ученик подключён" not in response.text
    assert _invite_row(student_id, "telegram") is None
    # Токен бота не трогается.
    assert _param(tutor_id, token_key("telegram")) == TELEGRAM_TOKEN


def test_unlink_no_js_redirects(client, monkeypatch):
    email = "invites-unlink2@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id(client, email)
    student_id = _create_student(client, "Ольга")
    _set_token(tutor_id, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}},
    )
    client.post(f"{_fragment_url(student_id)}/telegram/invite", headers=HTMX)

    response = client.post(
        f"{_fragment_url(student_id)}/telegram/unlink", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tutor/students/{student_id}"
    assert _invite_row(student_id, "telegram") is None


def test_invites_isolated_by_tutor(client, monkeypatch):
    """Ученик репетитора A недоступен репетитору B — 404, не пустая страница."""
    email_a = "invites-a@example.com"
    email_b = "invites-b@example.com"
    _register_and_login(client, email_a)
    tutor_a = _tutor_id(client, email_a)
    student_a = _create_student(client, "Ольга")
    _set_token(tutor_a, "telegram", TELEGRAM_TOKEN)
    _patch_urlopen(
        monkeypatch,
        {"/getMe": {"ok": True, "result": {"id": 1, "username": "tutor_bot"}}},
    )
    client.post(f"{_fragment_url(student_a)}/telegram/invite", headers=HTMX)
    saved = _invite_fields(student_a, "telegram")

    _register_and_login(client, email_b)
    assert client.get(_fragment_url(student_a)).status_code == 404
    assert client.post(
        f"{_fragment_url(student_a)}/telegram/invite", headers=HTMX
    ).status_code == 404
    assert client.post(
        f"{_fragment_url(student_a)}/telegram/unlink", headers=HTMX
    ).status_code == 404
    assert _invite_fields(student_a, "telegram") == saved
