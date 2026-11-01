"""Тесты синхронизации занятий с Google Календарём.

Проверяется поведение сервисов и вьюх: событие создаётся, правится при
переносе и удаляется вместе с уроком; ошибка Google не ломает действие
пользователя. Сетевой транспорт подменяется (`urllib.request.urlopen`),
как в `tests/test_notification_channels.py`.
"""

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from io import BytesIO

from app.config import settings as app_settings
from app.database import SessionLocal
from app.gcalendar.models.calendar_event import CalendarEvent
from app.gcalendar.services import connection, mapping
from app.gcalendar.services.sync import (
    OUTCOME_CREATED,
    OUTCOME_FAILED,
    OUTCOME_SKIPPED,
    OUTCOME_UPDATED,
    sync_lesson,
)
from app.lesson.models.lesson import Lesson
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow

PASSWORD = "Секретный-Пароль-1"
CLIENT_ID = "test-client-id.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret"

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars"

# ---------------------------------------------------------------------------
# Вспомогательное: транспорт, вход, подключение календаря
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

def _patch_api(monkeypatch, calls, *, insert_id="event-1", error=None):
    """Подменяет urlopen: пишет вызовы, отвечает по методу запроса."""

    def fake_urlopen(request, timeout=None, context=None):
        method = request.get_method()
        raw = request.data
        calls.append({
            "method": method,
            "url": request.full_url,
            "data": json.loads(raw.decode()) if raw else None,
        })
        if error is not None:
            raise error
        if method == "POST":
            return _FakeResponse({"id": insert_id})
        if method == "GET":
            return _FakeResponse({"items": []})
        return _FakeResponse({})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

def _configure(monkeypatch, *, client_id=CLIENT_ID, secret=CLIENT_SECRET, sync=True):
    monkeypatch.setattr(app_settings, "google_client_id", client_id)
    monkeypatch.setattr(app_settings, "google_client_secret", secret)
    monkeypatch.setattr(app_settings, "google_calendar_sync", sync)

def _connect(tutor_id, *, access="access-1", refresh="refresh-1"):
    """Сохраняет «подключённый» календарь: действующий access_token."""
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

def _lesson(lesson_id):
    with SessionLocal() as db:
        return db.get(Lesson, lesson_id)

def _tutor(tutor_id):
    with SessionLocal() as db:
        return db.get(Tutor, tutor_id)

def _event_row(lesson_id):
    with SessionLocal() as db:
        return mapping.get(db, lesson_id)

def _register_and_login(client, email):
    client.post(
        "/tutor/register",
        data={
            "name": "Синхронизация",
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

def _future(days=1, hour=10):
    """Будущий момент в UTC: урок не должен зависеть от даты прогона."""
    moment = (utcnow() + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return moment

# ---------------------------------------------------------------------------
# Сервис: создать, обновить, пропустить
# ---------------------------------------------------------------------------

def test_sync_creates_event_with_local_time(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Создание урока создаёт событие; время — настенное в зоне педагога."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-42")
    tutor_id = tutor_factory(timezone="Europe/Moscow")
    _connect(tutor_id)
    lesson_id = lesson_factory(
        student_id=student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Петров"),
        status="planned",
        starts_at=datetime(2027, 3, 10, 7, 0, tzinfo=UTC),  # 10:00 MSK
        duration_min=60,
        price=2000,
    )

    with SessionLocal() as db:
        outcome = sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))

    assert outcome == OUTCOME_CREATED
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"].startswith(f"{EVENTS_URL}/primary/events")
    body = calls[0]["data"]
    assert body["summary"] == "Занятие — Иван Петров"
    assert body["start"]["dateTime"] == "2027-03-10T10:00:00"
    assert body["start"]["timeZone"] == "Europe/Moscow"
    assert body["end"]["dateTime"] == "2027-03-10T11:00:00"
    assert "Стоимость: 2000 ₽" in body["description"]

    row = _event_row(lesson_id)
    assert row is not None
    assert row.event_id == "event-42"
    assert row.calendar_id == "primary"
    assert len(row.content_hash) == 64

def test_sync_patches_event_on_time_change(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Смена времени урока правит существующее событие, а не создаёт новое."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-7")
    tutor_id = tutor_factory()
    _connect(tutor_id)
    lesson_id = lesson_factory(
        student_id=student_factory(tutor_id=tutor_id),
        status="planned",
        starts_at=datetime(2027, 3, 10, 10, 0, tzinfo=UTC),
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        sync_lesson(db, tutor, db.get(Lesson, lesson_id))
        before = _event_row(lesson_id).content_hash

    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        lesson.starts_at = datetime(2027, 3, 10, 12, 0, tzinfo=UTC)
        db.commit()
        outcome = sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))

    assert outcome == OUTCOME_UPDATED
    assert len(calls) == 2
    assert calls[1]["method"] == "PATCH"
    assert "/events/event-7" in calls[1]["url"]
    assert calls[1]["data"]["start"]["dateTime"] == "2027-03-10T12:00:00"
    assert _event_row(lesson_id).content_hash != before

def test_sync_without_changes_makes_no_requests(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Повторная синхронизация неизменённого урока не ходит в Google."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-1")
    tutor_id = tutor_factory()
    lesson_id = lesson_factory(student_id=student_factory(tutor_id=tutor_id), status="planned")

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        sync_lesson(db, tutor, db.get(Lesson, lesson_id))
    calls.clear()

    with SessionLocal() as db:
        outcome = sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))

    assert outcome == OUTCOME_SKIPPED
    assert calls == []

def test_sync_skips_without_connection(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """При неподключённом календаре запросов к API нет вовсе."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls)
    tutor_id = tutor_factory()
    lesson_id = lesson_factory(student_id=student_factory(tutor_id=tutor_id), status="planned")

    with SessionLocal() as db:
        outcome = sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))

    assert outcome == OUTCOME_SKIPPED
    assert calls == []
    assert _event_row(lesson_id) is None

def test_sync_disabled_by_flag(monkeypatch, tutor_factory, student_factory, lesson_factory):
    """Флаг GOOGLE_CALENDAR_SYNC=false выключает синхронизацию целиком."""
    _configure(monkeypatch, sync=False)
    calls = []
    _patch_api(monkeypatch, calls)
    tutor_id = tutor_factory()
    _connect(tutor_id)
    lesson_id = lesson_factory(student_id=student_factory(tutor_id=tutor_id), status="planned")

    with SessionLocal() as db:
        outcome = sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))

    assert outcome == OUTCOME_SKIPPED
    assert calls == []

def test_sync_api_error_does_not_raise(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Недоступность Google не ломает сохранение и пишет текст в карточку."""
    _configure(monkeypatch)
    error = urllib.error.URLError("нет сети")
    _patch_api(monkeypatch, [], error=error)
    tutor_id = tutor_factory()
    _connect(tutor_id)
    lesson_id = lesson_factory(student_id=student_factory(tutor_id=tutor_id), status="planned")

    with SessionLocal() as db:
        outcome = sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))
        last_error = connection.last_error(db, tutor_id)

    assert outcome == OUTCOME_FAILED
    assert "сеть недоступна" in last_error
    assert _event_row(lesson_id) is None

def test_sync_unauthorized_refreshes_token(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """401 от API: токен обновляется по refresh_token и запрос повторяется."""
    _configure(monkeypatch)
    calls = []

    class _Refreshed:
        """token endpoint отдаёт новый access_token."""

        def __init__(self, payload):
            self._body = json.dumps(payload).encode()

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None, context=None):
        url = request.full_url
        calls.append({"url": url, "method": request.get_method()})
        if "oauth2.googleapis.com/token" in url:
            return _Refreshed({"access_token": "access-2", "expires_in": 3600})
        if request.get_method() == "POST" and "access-1" in request.get_header("Authorization", ""):
            raise urllib.error.HTTPError(url, 401, "Unauthorized", None, BytesIO(b"{}"))
        return _Refreshed({"id": "event-9"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    tutor_id = tutor_factory()
    _connect(tutor_id, access="access-1")
    lesson_id = lesson_factory(student_id=student_factory(tutor_id=tutor_id), status="planned")

    with SessionLocal() as db:
        outcome = sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))

    assert outcome == OUTCOME_CREATED
    assert any("oauth2.googleapis.com/token" in call["url"] for call in calls)
    assert _event_row(lesson_id).event_id == "event-9"

def test_delete_lesson_event_removes_row_and_event(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Удаление события урока чистит и Google, и строку соответствия."""
    from app.gcalendar.services.sync import delete_lesson_event

    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-5")
    tutor_id = tutor_factory()
    _connect(tutor_id)
    lesson_id = lesson_factory(student_id=student_factory(tutor_id=tutor_id), status="planned")

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        sync_lesson(db, tutor, db.get(Lesson, lesson_id))
    calls.clear()

    with SessionLocal() as db:
        ok = delete_lesson_event(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))

    assert ok is True
    assert calls[0]["method"] == "DELETE"
    assert "/events/event-5" in calls[0]["url"]
    assert _event_row(lesson_id) is None

# ---------------------------------------------------------------------------
# Вьюхи: жизненный цикл урока
#
# В этих тестах репетитор создаётся регистрацией через клиент: сессия
# указывает именно на него, и `tutor_id` берётся из БД по email — иначе
# уроки принадлежали бы другому репетитору, чем тот, что вошёл.
# ---------------------------------------------------------------------------

def _tutor_by_email(email):
    from sqlalchemy import text

    with SessionLocal() as db:
        return db.execute(
            text("select id from tutors where email = :e"), {"e": email}
        ).scalar()

def test_create_lesson_view_syncs_event(
    monkeypatch, client, tutor_factory, student_factory
):
    """Создание урока через форму создаёт событие в Google."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-view-1")
    _register_and_login(client, "sync-create@example.com")
    tutor_id = _tutor_by_email("sync-create@example.com")
    _connect(tutor_id)
    student_id = student_factory(tutor_id=tutor_id, first_name="Пётр")

    response = client.post(
        "/tutor/lessons",
        data={
            "type": "individual",
            "student_id": student_id,
            "starts_at": "2027-05-04T15:00",
            "duration_min": "60",
            "price": "1500",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"

def test_create_lesson_view_survives_google_error(
    monkeypatch, client, tutor_factory, student_factory
):
    """Ошибка Google не мешает созданию урока через форму."""
    _configure(monkeypatch)
    _patch_api(monkeypatch, [], error=urllib.error.URLError("нет сети"))
    _register_and_login(client, "sync-create-err@example.com")
    tutor_id = _tutor_by_email("sync-create-err@example.com")
    _connect(tutor_id)
    student_id = student_factory(tutor_id=tutor_id, first_name="Пётр")

    response = client.post(
        "/tutor/lessons",
        data={
            "type": "individual",
            "student_id": student_id,
            "starts_at": "2027-05-04T15:00",
            "duration_min": "60",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "lesson-saved"
    with SessionLocal() as db:
        assert db.query(Lesson).filter_by(student_id=student_id).count() == 1

def test_update_lesson_view_patches_event(
    monkeypatch, client, tutor_factory, student_factory, lesson_factory
):
    """Правка урока (смена времени) правит событие, а не создаёт новое."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-upd-1")
    _register_and_login(client, "sync-update@example.com")
    tutor_id = _tutor_by_email("sync-update@example.com")
    _connect(tutor_id)
    student_id = student_factory(tutor_id=tutor_id, first_name="Анна")
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 6, 1, 9, 0, tzinfo=UTC),
    )
    with SessionLocal() as db:
        sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))
    calls.clear()

    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data={
            "type": "individual",
            "student_id": student_id,
            "starts_at": "2027-06-01T12:00",
            "duration_min": "60",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert [call["method"] for call in calls] == ["PATCH"]
    assert calls[0]["data"]["start"]["dateTime"] == "2027-06-01T12:00:00"

def test_move_lesson_view_patches_event(
    monkeypatch, client, tutor_factory, student_factory, lesson_factory
):
    """Перенос урока перетаскиванием правит событие."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-move-1")
    _register_and_login(client, "sync-move@example.com")
    tutor_id = _tutor_by_email("sync-move@example.com")
    _connect(tutor_id)
    lesson_id = lesson_factory(
        student_id=student_factory(tutor_id=tutor_id),
        status="planned",
        starts_at=datetime(2027, 6, 1, 9, 0, tzinfo=UTC),
    )
    # Урок создан фабрикой в обход вьюхи — событие создаём вручную.
    with SessionLocal() as db:
        sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))
    calls.clear()

    response = client.post(
        f"/tutor/lessons/{lesson_id}/move",
        data={"date": "2027-06-02", "time": "11:00"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["data"]["start"]["dateTime"] == "2027-06-02T11:00:00"

def test_delete_lesson_view_deletes_event_before_lesson(
    monkeypatch, client, tutor_factory, student_factory, lesson_factory
):
    """Удаление урока сначала удаляет событие — иначе id теряется каскадом."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-del-1")
    _register_and_login(client, "sync-del@example.com")
    tutor_id = _tutor_by_email("sync-del@example.com")
    _connect(tutor_id)
    lesson_id = lesson_factory(
        student_id=student_factory(tutor_id=tutor_id), status="planned",
        starts_at=datetime(2027, 7, 1, 9, 0, tzinfo=UTC),
    )
    with SessionLocal() as db:
        sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))
    calls.clear()

    response = client.post(
        f"/tutor/lessons/{lesson_id}/delete", headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    assert [call["method"] for call in calls] == ["DELETE"]
    assert "/events/event-del-1" in calls[0]["url"]
    with SessionLocal() as db:
        assert db.get(Lesson, lesson_id) is None
        assert db.query(CalendarEvent).filter_by(lesson_id=lesson_id).count() == 0

def test_delete_series_view_deletes_all_events(
    monkeypatch, client, tutor_factory, student_factory, lesson_factory
):
    """Удаление серии удаляет события всех её уроков."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-series-1")
    _register_and_login(client, "sync-series@example.com")
    tutor_id = _tutor_by_email("sync-series@example.com")
    _connect(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)

    from app.lesson.models.lesson_series import LessonSeries

    with SessionLocal() as db:
        series = LessonSeries(slots=[{"weekday": 0, "time": "10:00"}], interval_weeks=1,
                              until_date=datetime(2027, 8, 1).date())
        db.add(series)
        db.commit()
        series_id = series.id

    lesson_ids = [
        lesson_factory(
            student_id=student_id, status="planned", series_id=series_id,
            starts_at=datetime(2027, 7, day, 9, 0, tzinfo=UTC),
        )
        for day in (1, 8)
    ]
    with SessionLocal() as db:
        for lesson_id in lesson_ids:
            sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))
    calls.clear()

    response = client.post(
        f"/tutor/lessons/{lesson_ids[0]}/delete-series",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert [call["method"] for call in calls] == ["DELETE", "DELETE"]
    with SessionLocal() as db:
        assert db.query(Lesson).filter(Lesson.series_id == series_id).count() == 0

def test_delete_group_view_deletes_lesson_events(
    monkeypatch, client, tutor_factory, group_factory, lesson_factory
):
    """Удаление группы удаляет события её уроков до каскада."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls, insert_id="event-group-1")
    _register_and_login(client, "sync-group@example.com")
    tutor_id = _tutor_by_email("sync-group@example.com")
    _connect(tutor_id)
    group_id = group_factory(tutor_id=tutor_id)
    lesson_id = lesson_factory(
        group_id=group_id, status="planned",
        starts_at=datetime(2027, 9, 1, 9, 0, tzinfo=UTC),
    )
    with SessionLocal() as db:
        sync_lesson(db, db.get(Tutor, tutor_id), db.get(Lesson, lesson_id))
    calls.clear()

    response = client.post(
        f"/tutor/groups/{group_id}/delete", headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    assert [call["method"] for call in calls] == ["DELETE"]
    with SessionLocal() as db:
        assert db.get(Lesson, lesson_id) is None
        assert db.query(CalendarEvent).filter_by(lesson_id=lesson_id).count() == 0

def test_foreign_lesson_is_not_synced(
    monkeypatch, client, tutor_factory, student_factory, lesson_factory
):
    """Чужой урок недоступен: 404 и ни одного запроса к Google."""
    _configure(monkeypatch)
    calls = []
    _patch_api(monkeypatch, calls)
    owner_id = tutor_factory()
    foreign_student = student_factory(tutor_id=owner_id)
    foreign_lesson = lesson_factory(
        student_id=foreign_student, status="planned"
    )
    _register_and_login(client, "sync-foreign@example.com")
    tutor_id = _tutor_by_email("sync-foreign@example.com")
    _connect(tutor_id)

    response = client.post(
        f"/tutor/lessons/{foreign_lesson}/move",
        data={"date": "2027-06-02", "time": "11:00"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 404
    assert calls == []
