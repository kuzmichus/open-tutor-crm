"""Тесты OAuth-подключения Google Календаря: ссылка, код, токены, отзыв.

Поведение проверяется через HTTP тем же путём, что у пользователя, а
сетевой транспорт подменяется (`urllib.request.urlopen`) — как в
`tests/test_notification_channels.py`: сеть в тестах не дёргается, но
код вызова тот же, что в бою.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO

from app.config import settings as app_settings
from app.database import SessionLocal
from app.gcalendar.services import connection, oauth
from app.gcalendar.services.errors import GoogleApiError, GoogleReauthRequired
from app.tutor.services.params import get_param, set_param

PASSWORD = "Секретный-Пароль-1"
CLIENT_ID = "test-client-id.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret"

TAB_URL = "/tutor/profile?tab=calendar"
CONNECT_URL = "/tutor/profile/google/connect"
CALLBACK_URL = "/tutor/profile/google/callback"
DISCONNECT_URL = "/tutor/profile/google/disconnect"

# ---------------------------------------------------------------------------
# Вспомогательное: окружение, вход, транспорт
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

def _patch_urlopen(monkeypatch, responder, calls):
    """Подменяет urlopen; каждый вызов (URL, метод, тело) — в `calls`.

    Тело разбирается «как получится»: token endpoint ждёт urlencoded,
    Calendar API — JSON, и заглушка не должна диктовать формат.
    """

    def fake_urlopen(request, timeout=None, context=None):
        raw = request.data
        calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "data": _body(raw),
            "headers": {
                name.lower(): value for name, value in request.header_items()
            },
        })
        answer = responder(calls[-1]["url"], calls[-1])
        if isinstance(answer, Exception):
            raise answer
        return _FakeResponse(answer)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

def _body(raw):
    """Тело запроса: JSON, urlencoded-форма или None — без исключений."""
    if not raw:
        return None
    text = raw.decode()
    try:
        return json.loads(text)
    except ValueError:
        return dict(urllib.parse.parse_qsl(text))

def _routes(routes):
    """Ответ по подстроке URL; значение — payload или исключение."""

    def responder(url, call):
        for fragment, answer in routes.items():
            if fragment in url:
                return answer
        raise AssertionError(f"нет заглушки для {url}")

    return responder

def _configure(monkeypatch, *, client_id=CLIENT_ID, secret=CLIENT_SECRET):
    """Креды OAuth в настройках: по умолчанию пустые, тест их задаёт явно."""
    monkeypatch.setattr(app_settings, "google_client_id", client_id)
    monkeypatch.setattr(app_settings, "google_client_secret", secret)

def _register_and_login(client, email):
    client.post(
        "/tutor/register",
        data={
            "name": "Google Календарь",
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

def _tutor_id(email):
    from sqlalchemy import text

    with SessionLocal() as db:
        return db.execute(
            text("select id from tutors where email = :e"), {"e": email}
        ).scalar()

def _param(tutor_id, key):
    with SessionLocal() as db:
        return get_param(db, tutor_id, key)

def _set_param(tutor_id, key, value):
    with SessionLocal() as db:
        set_param(db, tutor_id, key, value)

# ---------------------------------------------------------------------------
# Настройка интеграции и ссылка согласия
# ---------------------------------------------------------------------------

def test_not_configured_by_default():
    """Без кредов в окружении интеграция выключена."""
    assert oauth.configured() is False

def test_configured_needs_both_values(monkeypatch):
    monkeypatch.setattr(app_settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(app_settings, "google_client_secret", "")
    assert oauth.configured() is False

def test_auth_url_contains_client_scope_and_state(monkeypatch):
    _configure(monkeypatch)
    url = oauth.build_auth_url("https://crm.example.com/cb", "state-123")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert CLIENT_ID in url
    assert "calendar.events" in url
    assert "state-123" in url
    # offline + consent: без них Google не отдаст refresh_token повторно.
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "redirect_uri=https%3A%2F%2Fcrm.example.com%2Fcb" in url

def test_auth_url_without_credentials_raises(monkeypatch):
    monkeypatch.setattr(app_settings, "google_client_id", "")
    monkeypatch.setattr(app_settings, "google_client_secret", "")
    try:
        oauth.build_auth_url("https://crm.example.com/cb", "state")
    except Exception as exc:  # noqa: BLE001 — проверяем тип
        from app.gcalendar.services.errors import GoogleNotConfigured

        assert isinstance(exc, GoogleNotConfigured)
    else:
        raise AssertionError("ожидался GoogleNotConfigured")

# ---------------------------------------------------------------------------
# Обмен кода и обновление токена
# ---------------------------------------------------------------------------

def test_exchange_code_sends_redirect_uri(monkeypatch):
    """Обмен идёт с тем же redirect_uri, что был в ссылке согласия."""
    _configure(monkeypatch)
    calls = []
    _patch_urlopen(monkeypatch, _routes({
        "oauth2.googleapis.com/token": {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
        },
    }), calls)

    body = oauth.exchange_code("code-1", "https://crm.example.com/cb")

    assert body["refresh_token"] == "refresh-1"
    sent = calls[0]["data"]
    assert sent["code"] == "code-1"
    assert sent["redirect_uri"] == "https://crm.example.com/cb"
    assert sent["grant_type"] == "authorization_code"

def test_refresh_token_invalid_grant_requires_reauth(monkeypatch):
    """`invalid_grant` — не общая ошибка, а требование подключиться заново."""
    _configure(monkeypatch)
    error = urllib.error.HTTPError(
        "https://oauth2.googleapis.com/token",
        400,
        "Bad Request",
        None,
        BytesIO(json.dumps({
            "error": "invalid_grant",
            "error_description": "Token has been expired or revoked.",
        }).encode()),
    )
    _patch_urlopen(monkeypatch, _routes({"oauth2.googleapis.com/token": error}), [])

    try:
        oauth.refresh_access_token("dead-token")
    except GoogleReauthRequired:
        return
    raise AssertionError("ожидался GoogleReauthRequired")

def test_token_endpoint_error_is_api_error(monkeypatch):
    _configure(monkeypatch)
    error = urllib.error.HTTPError(
        "https://oauth2.googleapis.com/token",
        500,
        "Server Error",
        None,
        BytesIO(b'{"error": "backend_error"}'),
    )
    _patch_urlopen(monkeypatch, _routes({"oauth2.googleapis.com/token": error}), [])

    try:
        oauth.refresh_access_token("token")
    except GoogleApiError as exc:
        assert "backend_error" in str(exc)
        return
    raise AssertionError("ожидался GoogleApiError")

def test_network_failure_is_api_error(monkeypatch):
    _configure(monkeypatch)
    _patch_urlopen(monkeypatch, _routes({
        "oauth2.googleapis.com/token": urllib.error.URLError("нет сети"),
    }), [])

    try:
        oauth.refresh_access_token("token")
    except GoogleApiError:
        return
    raise AssertionError("ожидался GoogleApiError")

# ---------------------------------------------------------------------------
# Хранение токенов
# ---------------------------------------------------------------------------

def test_access_token_refreshes_expired(tutor_factory, monkeypatch):
    """Истёкший access_token обновляется по refresh_token."""
    _configure(monkeypatch)
    tutor_id = tutor_factory()
    calls = []
    _patch_urlopen(monkeypatch, _routes({
        "oauth2.googleapis.com/token": {
            "access_token": "fresh-access",
            "expires_in": 3600,
        },
    }), calls)

    with SessionLocal() as db:
        connection.save_tokens(
            db,
            tutor_id,
            refresh_token="refresh-1",
            access_token="stale-access",
            expires_in=-10,  # уже истёк
        )
        db.commit()
        token = connection.access_token(db, tutor_id)

    assert token == "fresh-access"
    assert len(calls) == 1
    assert calls[0]["data"]["grant_type"] == "refresh_token"

def test_access_token_reused_while_valid(tutor_factory, monkeypatch):
    """Действующий токен не обновляется — лишнего запроса нет."""
    _configure(monkeypatch)
    tutor_id = tutor_factory()
    calls = []
    _patch_urlopen(monkeypatch, _routes({}), calls)

    with SessionLocal() as db:
        connection.save_tokens(
            db,
            tutor_id,
            refresh_token="refresh-1",
            access_token="valid-access",
            expires_in=3600,
        )
        db.commit()
        token = connection.access_token(db, tutor_id)

    assert token == "valid-access"
    assert calls == []

def test_access_token_none_without_connection(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        assert connection.access_token(db, tutor_id) is None

def test_clear_removes_all_google_params(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        connection.save_tokens(
            db,
            tutor_id,
            refresh_token="r",
            access_token="a",
            expires_in=3600,
            account_email="tutor@example.com",
        )
        connection.set_last_error(db, tutor_id, "ошибка")
        db.commit()
        connection.clear(db, tutor_id)

    assert _param(tutor_id, connection.REFRESH_TOKEN_KEY) is None
    assert _param(tutor_id, connection.ACCESS_TOKEN_KEY) is None
    assert _param(tutor_id, connection.ACCOUNT_EMAIL_KEY) is None
    assert _param(tutor_id, connection.LAST_ERROR_KEY) is None

def test_take_oauth_state_is_one_time(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        connection.save_oauth_state(db, tutor_id, "state-1")
        assert connection.take_oauth_state(db, tutor_id) == "state-1"
        assert connection.take_oauth_state(db, tutor_id) is None
