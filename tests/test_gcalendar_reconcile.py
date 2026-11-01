"""Тесты сверки Google Календаря (задание cron `gcalendar.reconcile`).

Сверка — страховка: она создаёт пропущенные события, правит изменившиеся
и удаляет осиротевшие. Проверяется идемпотентность (повторный прогон
ничего не меняет), окно сверки и изоляция сбоя одного репетитора.
"""

import json
import urllib.error
import urllib.request
from datetime import timedelta

from app.config import settings as app_settings
from app.database import SessionLocal
from app.gcalendar.models.calendar_event import CalendarEvent
from app.gcalendar.services import connection, mapping
from app.gcalendar.services.reconcile import (
    RECONCILE_FUTURE_DAYS,
    reconcile_all,
)
from app.lesson.models.lesson import Lesson
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow

CLIENT_ID = "test-client-id.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret"

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

def _patch_api(monkeypatch, calls, *, insert_id="event-new", remote_ids=()):
    """Подменяет urlopen: POST создаёт, GET отдаёт список событий календаря."""

    def fake_urlopen(request, timeout=None, context=None):
        method = request.get_method()
        calls.append({"method": method, "url": request.full_url})
        if method == "POST":
            return _FakeResponse({"id": insert_id})
        if method == "GET":
            return _FakeResponse({"items": [{"id": eid} for eid in remote_ids]})
        return _FakeResponse({})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

def _configure(monkeypatch):
    monkeypatch.setattr(app_settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(app_settings, "google_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(app_settings, "google_calendar_sync", True)

def _connect(tutor_id, *, access="access-1"):
    with SessionLocal() as db:
        connection.save_tokens(
            db,
            tutor_id,
            refresh_token="refresh-1",
            access_token=access,
            expires_in=3600,
        )

def _future(days=3, hour=10):
    return (utcnow() + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )

# ---------------------------------------------------------------------------
# Реестр cron
# ---------------------------------------------------------------------------

def test_registry_contains_reconcile():
    """В реестре заданий зарегистрирована сверка Google Календаря."""
    from app.common.services import cron as cron_module

    names = [name for name, _ in cron_module.TASKS]
    assert "gcalendar.reconcile" in names

def test_reconcile_is_registered_callable():
    """Регистрация указывает именно на сервис сверки."""
    from app.common.services import cron as cron_module
    from app.gcalendar.services import reconcile

    tasks = dict(cron_module.TASKS)
    assert tasks["gcalendar.reconcile"] is reconcile.reconcile_all

# ---------------------------------------------------------------------------
# Сверка
# ---------------------------------------------------------------------------

def test_reconcile_creates_missing_events(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Урок без события (хук не сработал) получает событие при сверке."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-reconciled")
    tutor_id = tutor_factory()
    _connect(tutor_id)
    lesson_id = lesson_factory(
        student_id=student_factory(tutor_id=tutor_id),
        status="planned",
        starts_at=_future(),
    )

    with SessionLocal() as db:
        changed = reconcile_all(db)

    assert changed == 1
    assert [call["method"] for call in calls if "calendar" in call["url"]] == ["POST"]
    row = None
    with SessionLocal() as db:
        row = mapping.get(db, lesson_id)
    assert row is not None
    assert row.event_id == "event-reconciled"

def test_reconcile_is_idempotent(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Повторный прогон ничего не меняет и не ходит в API создания."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-1")
    tutor_id = tutor_factory()
    _connect(tutor_id)
    lesson_factory(
        student_id=student_factory(tutor_id=tutor_id),
        status="planned",
        starts_at=_future(),
    )

    with SessionLocal() as db:
        assert reconcile_all(db) == 1
    calls.clear()
    with SessionLocal() as db:
        assert reconcile_all(db) == 0
    assert calls == []

def test_reconcile_skips_disconnected_tutors(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Репетитор без подключённого календаря не попадает в сверку."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls)
    tutor_id = tutor_factory()
    lesson_factory(
        student_id=student_factory(tutor_id=tutor_id),
        status="planned",
        starts_at=_future(),
    )

    with SessionLocal() as db:
        assert reconcile_all(db) == 0
    assert calls == []

def test_reconcile_ignores_lessons_outside_window(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Занятия за пределами окна сверки не выгружаются."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls)
    tutor_id = tutor_factory()
    _connect(tutor_id)
    lesson_factory(
        student_id=student_factory(tutor_id=tutor_id),
        status="planned",
        starts_at=_future(days=RECONCILE_FUTURE_DAYS + 10),
    )

    with SessionLocal() as db:
        assert reconcile_all(db) == 0
    assert [call for call in calls if "calendar" in call["url"]] == []

def test_reconcile_deletes_orphaned_events(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Событие урока, которого уже нет в БД, удаляется из календаря.

    Штатный путь удаления урока сначала удаляет событие, а каскад сносит
    строку соответствия. Сирота возможна, только если каскад не сработал
    (восстановление из бэкапа, прямой SQL при выключенных FK) — эту ветку
    и проверяем: строка соответствия ссылается на несуществующий урок.
    """
    from app.gcalendar.models.calendar_event import CalendarEvent as Row

    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, remote_ids=("event-orphan",))
    tutor_id = tutor_factory()
    _connect(tutor_id)

    # Урок «исчез» без каскада: строка соответствия ссылается на
    # несуществующий урок, события в БД для неё нет.
    orphan = Row(
        lesson_id="missing-lesson", event_id="event-orphan",
        calendar_id="primary", content_hash="0" * 64,
    )
    monkeypatch.setattr(
        mapping, "event_ids_of_tutor", lambda db, tid: {"event-orphan": orphan}
    )

    with SessionLocal() as db:
        changed = reconcile_all(db)

    assert changed == 1
    assert [call["method"] for call in calls if "calendar" in call["url"]] == ["GET", "DELETE"]
    with SessionLocal() as db:
        assert db.query(CalendarEvent).filter_by(event_id="event-orphan").count() == 0

def test_reconcile_tutor_failure_isolated(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Сбой одного репетитора не мешает сверке остальных."""
    _configure(monkeypatch)
    calls = []

    def fake_urlopen(request, timeout=None, context=None):
        calls.append({"method": request.get_method(), "url": request.full_url})
        if request.get_method() == "POST":
            raise urllib.error.URLError("нет сети")
        return _FakeResponse({"items": []})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    broken_id = tutor_factory()
    _connect(broken_id)
    lesson_factory(
        student_id=student_factory(tutor_id=broken_id),
        status="planned",
        starts_at=_future(days=5),
    )

    # Сверка не бросает: ошибка репетитора записывается в лог.
    with SessionLocal() as db:
        assert reconcile_all(db) == 0
    with SessionLocal() as db:
        assert "сеть недоступна" in connection.last_error(db, broken_id)
        # Подключение осталось: сетевая ошибка — не отзыв доступа.
        assert connection.is_connected(db, broken_id)

def test_reconcile_reauth_clears_connection(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Отозванный доступ сбрасывает подключение и не роняет задание."""
    _configure(monkeypatch)
    error = urllib.error.HTTPError(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        401,
        "Unauthorized",
        None,
        None,
    )

    def fake_urlopen(request, timeout=None, context=None):
        if "oauth2.googleapis.com/token" in request.full_url:
            raise urllib.error.HTTPError(
                request.full_url, 400, "Bad Request", None,
                _ErrorBody(b'{"error": "invalid_grant"}'),
            )
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    tutor_id = tutor_factory()
    _connect(tutor_id)
    lesson_factory(
        student_id=student_factory(tutor_id=tutor_id),
        status="planned",
        starts_at=_future(days=5),
    )

    with SessionLocal() as db:
        assert reconcile_all(db) == 0
    with SessionLocal() as db:
        assert not connection.is_connected(db, tutor_id)
        assert "подключите его заново" in connection.last_error(db, tutor_id)

class _ErrorBody:
    """Тело HTTPError: читается один раз, как у настоящего ответа."""

    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return self._raw

    def close(self):
        """HTTPError закрывает тело как файл — заглушка не должна падать."""
