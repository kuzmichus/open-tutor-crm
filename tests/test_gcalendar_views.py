"""Тесты блока «Google Календарь» в профиле и маршрутов подключения.

Поведение проверяется через HTTP тем же путём, что у пользователя:
разметка вкладки — по тексту и атрибутам, маршруты — по статусам и
редиректам. Сетевой транспорт подменяется (`urllib.request.urlopen`).
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from io import BytesIO

from app.config import settings as app_settings
from app.database import SessionLocal
from app.gcalendar.models.calendar_event import CalendarEvent
from app.gcalendar.services import connection
from app.lesson.models.lesson import Lesson
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow
from app.tutor.services.params import get_param

PASSWORD = "Секретный-Пароль-1"
CLIENT_ID = "test-client-id.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret"

TAB_URL = "/tutor/profile?tab=calendar"
CONNECT_URL = "/tutor/profile/google/connect"
CALLBACK_URL = "/tutor/profile/google/callback"
DISCONNECT_URL = "/tutor/profile/google/disconnect"

# ---------------------------------------------------------------------------
# Вспомогательное
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

def _patch_urlopen(monkeypatch, routes, calls):
    """Ответ по подстроке URL; каждый вызов — в `calls`."""

    def fake_urlopen(request, timeout=None, context=None):
        url = request.full_url
        raw = request.data
        calls.append({
            "url": url,
            "method": request.get_method(),
            "data": _body(raw),
        })
        for fragment, answer in routes.items():
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return _FakeResponse(answer)
        raise AssertionError(f"нет заглушки для {url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

def _body(raw):
    """Тело запроса: JSON, urlencoded-форма или None — без исключений.

    token endpoint и revoke ждут urlencoded, Calendar API — JSON; заглушка
    не должна диктовать формат.
    """
    if not raw:
        return None
    text = raw.decode()
    try:
        return json.loads(text)
    except ValueError:
        return dict(urllib.parse.parse_qsl(text))

def _configure(monkeypatch, *, client_id=CLIENT_ID, secret=CLIENT_SECRET):
    monkeypatch.setattr(app_settings, "google_client_id", client_id)
    monkeypatch.setattr(app_settings, "google_client_secret", secret)

def _register_and_login(client, email):
    client.post(
        "/tutor/register",
        data={
            "name": "Google Профиль",
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

def _connect(tutor_id, *, access="access-1", refresh="refresh-1"):
    with SessionLocal() as db:
        connection.save_tokens(
            db,
            tutor_id,
            refresh_token=refresh,
            access_token=access,
            expires_in=3600,
            account_email="tutor@example.com",
        )
        db.commit()

def _future(days=1, hour=10):
    moment = (utcnow() + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return moment

# ---------------------------------------------------------------------------
# Доступ
# ---------------------------------------------------------------------------

def test_connect_redirects_to_login_without_session(client):
    response = client.get(CONNECT_URL, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"

def test_callback_redirects_to_login_without_session(client):
    response = client.get(CALLBACK_URL, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"

def test_disconnect_redirects_to_login_without_session(client):
    response = client.post(DISCONNECT_URL, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"

# ---------------------------------------------------------------------------
# Карточка на вкладке
# ---------------------------------------------------------------------------

def test_tab_shows_google_block_with_connect_button(client, monkeypatch):
    _configure(monkeypatch)
    _register_and_login(client, "gcal-tab@example.com")
    html = client.get(TAB_URL).text
    assert "Google Календарь" in html
    assert "Подключить Google" in html
    assert CONNECT_URL in html

def test_tab_without_credentials_shows_hint(client, monkeypatch):
    """Без кредов на сервере кнопка неактивна и объясняет причину."""
    monkeypatch.setattr(app_settings, "google_client_id", "")
    monkeypatch.setattr(app_settings, "google_client_secret", "")
    _register_and_login(client, "gcal-nocreds@example.com")
    html = client.get(TAB_URL).text
    assert "Интеграция не настроена" in html
    assert "GOOGLE_CLIENT_ID" in html
    assert "disabled" in html

def test_tab_shows_connected_state(client, monkeypatch):
    _configure(monkeypatch)
    _register_and_login(client, "gcal-connected@example.com")
    tutor_id = _tutor_id("gcal-connected@example.com")
    _connect(tutor_id)

    html = client.get(TAB_URL).text
    assert "Календарь подключён" in html
    assert "tutor@example.com" in html
    assert DISCONNECT_URL in html
    assert "При отключении события останутся в календаре Google" in html

def test_tab_shows_last_error(client, monkeypatch):
    _configure(monkeypatch)
    _register_and_login(client, "gcal-error@example.com")
    tutor_id = _tutor_id("gcal-error@example.com")
    _connect(tutor_id)
    with SessionLocal() as db:
        connection.set_last_error(db, tutor_id, "Google: сеть недоступна.")

    html = client.get(TAB_URL).text
    assert "Google: сеть недоступна." in html

# ---------------------------------------------------------------------------
# Начало подключения
# ---------------------------------------------------------------------------

def test_connect_redirects_to_google_with_state(client, monkeypatch):
    _configure(monkeypatch)
    _register_and_login(client, "gcal-connect@example.com")

    response = client.get(CONNECT_URL, follow_redirects=False)

    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "state=" in location
    tutor_id = _tutor_id("gcal-connect@example.com")
    assert _param(tutor_id, connection.OAUTH_STATE_KEY)

def test_connect_without_credentials_returns_hint(client, monkeypatch):
    monkeypatch.setattr(app_settings, "google_client_id", "")
    monkeypatch.setattr(app_settings, "google_client_secret", "")
    _register_and_login(client, "gcal-connect-nocreds@example.com")

    response = client.get(CONNECT_URL, follow_redirects=False)

    assert response.status_code == 303
    assert "google_error=not_configured" in response.headers["location"]

def test_tab_renders_error_from_query(client, monkeypatch):
    _configure(monkeypatch)
    _register_and_login(client, "gcal-query-error@example.com")
    html = client.get(f"{TAB_URL}&google_error=denied").text
    assert "Доступ к Google Календарю не предоставлен" in html

# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

def test_callback_with_wrong_state_saves_nothing(client, monkeypatch):
    _configure(monkeypatch)
    _register_and_login(client, "gcal-badstate@example.com")
    tutor_id = _tutor_id("gcal-badstate@example.com")
    with SessionLocal() as db:
        connection.save_oauth_state(db, tutor_id, "right-state")
    calls = []
    _patch_urlopen(monkeypatch, {}, calls)

    response = client.get(
        f"{CALLBACK_URL}?code=code-1&state=wrong-state", follow_redirects=False
    )

    assert response.status_code == 303
    assert "google_error=state" in response.headers["location"]
    assert calls == []
    assert _param(tutor_id, connection.REFRESH_TOKEN_KEY) is None

def test_callback_state_is_one_time(client, monkeypatch):
    """Второй callback с тем же state отклоняется."""
    _configure(monkeypatch)
    _register_and_login(client, "gcal-replay@example.com")
    tutor_id = _tutor_id("gcal-replay@example.com")
    with SessionLocal() as db:
        connection.save_oauth_state(db, tutor_id, "state-1")
    calls = []
    _patch_urlopen(monkeypatch, {
        "oauth2.googleapis.com/token": {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
        },
        "userinfo": {"email": "tutor@example.com"},
        "googleapis.com/calendar": {"id": "event-1"},
    }, calls)

    first = client.get(
        f"{CALLBACK_URL}?code=code-1&state=state-1", follow_redirects=False
    )
    assert "saved=1" in first.headers["location"]

    second = client.get(
        f"{CALLBACK_URL}?code=code-1&state=state-1", follow_redirects=False
    )
    assert "google_error=state" in second.headers["location"]

def test_callback_access_denied_saves_nothing(client, monkeypatch):
    _configure(monkeypatch)
    _register_and_login(client, "gcal-denied@example.com")
    tutor_id = _tutor_id("gcal-denied@example.com")
    with SessionLocal() as db:
        connection.save_oauth_state(db, tutor_id, "state-1")

    response = client.get(
        f"{CALLBACK_URL}?error=access_denied&state=state-1",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "google_error=denied" in response.headers["location"]
    assert _param(tutor_id, connection.REFRESH_TOKEN_KEY) is None

def test_callback_saves_tokens_and_email(client, monkeypatch):
    _configure(monkeypatch)
    _register_and_login(client, "gcal-success@example.com")
    tutor_id = _tutor_id("gcal-success@example.com")
    with SessionLocal() as db:
        connection.save_oauth_state(db, tutor_id, "state-1")
    calls = []
    _patch_urlopen(monkeypatch, {
        "oauth2.googleapis.com/token": {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
        },
        "userinfo": {"email": "tutor@example.com"},
    }, calls)

    response = client.get(
        f"{CALLBACK_URL}?code=code-1&state=state-1", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"{TAB_URL}&saved=1"
    with SessionLocal() as db:
        assert connection.is_connected(db, tutor_id)
        assert connection.account_email(db, tutor_id) == "tutor@example.com"
        assert connection.calendar_id(db, tutor_id) == "primary"

def test_callback_exchanges_code_with_same_redirect_uri(client, monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(
        app_settings, "google_redirect_uri", "https://crm.example.com/tutor/profile/google/callback"
    )
    _register_and_login(client, "gcal-redirect@example.com")
    tutor_id = _tutor_id("gcal-redirect@example.com")
    with SessionLocal() as db:
        connection.save_oauth_state(db, tutor_id, "state-1")
    calls = []
    _patch_urlopen(monkeypatch, {
        "oauth2.googleapis.com/token": {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
        },
        "userinfo": {"email": "tutor@example.com"},
    }, calls)

    client.get(f"{CALLBACK_URL}?code=code-1&state=state-1", follow_redirects=False)

    token_call = next(call for call in calls if "oauth2.googleapis.com/token" in call["url"])
    assert token_call["data"]["redirect_uri"] == (
        "https://crm.example.com/tutor/profile/google/callback"
    )

def test_callback_uploads_future_lessons_only(
    client, monkeypatch, student_factory, lesson_factory
):
    """Первичная выгрузка: будущие занятия — да, прошедшие — нет."""
    _configure(monkeypatch)
    _register_and_login(client, "gcal-initial@example.com")
    tutor_id = _tutor_id("gcal-initial@example.com")
    student_id = student_factory(tutor_id=tutor_id, first_name="Мария")
    future_id = lesson_factory(
        student_id=student_id, status="planned", starts_at=_future(days=3)
    )
    past_id = lesson_factory(
        student_id=student_id, status="planned", starts_at=_future(days=-3)
    )
    with SessionLocal() as db:
        connection.save_oauth_state(db, tutor_id, "state-1")
    calls = []
    _patch_urlopen(monkeypatch, {
        "oauth2.googleapis.com/token": {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
        },
        "userinfo": {"email": "tutor@example.com"},
        "googleapis.com/calendar": {"id": "event-1"},
    }, calls)

    client.get(f"{CALLBACK_URL}?code=code-1&state=state-1", follow_redirects=False)

    inserts = [
        call for call in calls
        if call["method"] == "POST" and "googleapis.com/calendar" in call["url"]
    ]
    assert len(inserts) == 1
    with SessionLocal() as db:
        assert db.query(CalendarEvent).filter_by(lesson_id=future_id).count() == 1
        assert db.query(CalendarEvent).filter_by(lesson_id=past_id).count() == 0

def test_callback_exchange_failure_keeps_disconnected(client, monkeypatch):
    """Неудачный обмен кода не оставляет полуподключения."""
    _configure(monkeypatch)
    _register_and_login(client, "gcal-exchange@example.com")
    tutor_id = _tutor_id("gcal-exchange@example.com")
    with SessionLocal() as db:
        connection.save_oauth_state(db, tutor_id, "state-1")
    error = urllib.error.HTTPError(
        "https://oauth2.googleapis.com/token", 400, "Bad Request", None,
        BytesIO(b'{"error": "invalid_client"}'),
    )
    _patch_urlopen(monkeypatch, {"oauth2.googleapis.com/token": error}, [])

    response = client.get(
        f"{CALLBACK_URL}?code=code-1&state=state-1", follow_redirects=False
    )

    assert "google_error=exchange" in response.headers["location"]
    with SessionLocal() as db:
        assert not connection.is_connected(db, tutor_id)

# ---------------------------------------------------------------------------
# Отключение
# ---------------------------------------------------------------------------

def test_disconnect_clears_tokens_and_mappings(
    client, monkeypatch, student_factory, lesson_factory
):
    _configure(monkeypatch)
    _register_and_login(client, "gcal-disconnect@example.com")
    tutor_id = _tutor_id("gcal-disconnect@example.com")
    _connect(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    lesson_id = lesson_factory(
        student_id=student_id, status="planned", starts_at=_future(days=2)
    )
    with SessionLocal() as db:
        from app.gcalendar.services import mapping

        mapping.upsert(
            db, lesson_id, event_id="event-1", calendar_id="primary",
            content_hash="0" * 64,
        )
        db.commit()
    calls = []
    _patch_urlopen(monkeypatch, {"oauth2.googleapis.com/revoke": {}}, calls)

    response = client.post(DISCONNECT_URL, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == TAB_URL
    assert any("oauth2.googleapis.com/revoke" in call["url"] for call in calls)
    with SessionLocal() as db:
        assert not connection.is_connected(db, tutor_id)
        assert connection.account_email(db, tutor_id) == ""
        assert db.query(CalendarEvent).filter_by(lesson_id=lesson_id).count() == 0

def test_disconnect_survives_revoke_failure(client, monkeypatch):
    """Недоступность Google не мешает локальному отключению."""
    _configure(monkeypatch)
    _register_and_login(client, "gcal-revoke-fail@example.com")
    tutor_id = _tutor_id("gcal-revoke-fail@example.com")
    _connect(tutor_id)
    _patch_urlopen(monkeypatch, {
        "oauth2.googleapis.com/revoke": urllib.error.URLError("нет сети"),
    }, [])

    response = client.post(DISCONNECT_URL, follow_redirects=False)

    assert response.status_code == 303
    with SessionLocal() as db:
        assert not connection.is_connected(db, tutor_id)

def test_disconnect_keeps_lessons(client, monkeypatch, student_factory, lesson_factory):
    """Отключение не удаляет занятия в CRM — только связь с Google."""
    _configure(monkeypatch)
    _register_and_login(client, "gcal-keep@example.com")
    tutor_id = _tutor_id("gcal-keep@example.com")
    _connect(tutor_id)
    lesson_id = lesson_factory(
        student_id=student_factory(tutor_id=tutor_id),
        status="planned",
        starts_at=_future(days=2),
    )
    _patch_urlopen(monkeypatch, {"oauth2.googleapis.com/revoke": {}}, [])

    client.post(DISCONNECT_URL, follow_redirects=False)

    with SessionLocal() as db:
        assert db.get(Lesson, lesson_id) is not None
