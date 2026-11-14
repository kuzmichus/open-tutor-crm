"""Оповещения об изменении урока: HTTP → стандартный транспорт → журнал."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_series import LessonSeries
from app.messenger.models.sent_message import SentMessage
from app.messenger.models.student_invite import StudentMessengerInvite
from app.messenger.services.errors import SendError
from app.messenger.services.max_sender import MaxSender
from app.messenger.services.telegram_sender import TelegramSender
from app.tutor.services.params import set_param
from app.tutor.services.settings import save_settings

START = datetime(2027, 1, 10, 22, 30, tzinfo=UTC)


@pytest.fixture()
def owner(client, tutor_factory):
    """Авторизованный репетитор с UTC-вводом формы."""
    tutor_id = tutor_factory(email="changes@example.com", password="Password-123")
    client.post("/tutor/login", data={"email": "changes@example.com", "password": "Password-123"})
    return tutor_id


@pytest.fixture()
def deliveries(monkeypatch):
    """Подменяет только транспорт, сохраняя реальные ретраи и журнал."""
    calls = []
    for channel, sender in (("telegram", TelegramSender), ("max", MaxSender)):
        def send(self, config, recipient, text, channel=channel):
            calls.append((channel, recipient, text))
        monkeypatch.setattr(sender, "send", send)
    return calls


def bind(tutor_id, student_id, channels=("telegram",)):
    """Привязанные чаты ученика и токены ботов."""
    with SessionLocal() as db:
        for channel in channels:
            set_param(db, tutor_id, f"{channel}_token", "test-token")
            db.add(StudentMessengerInvite(tutor_id=tutor_id, student_id=student_id,
                                          messenger=channel, chat_id=f"{student_id}-{channel}"))
        db.commit()


def form(student_id, **extra):
    """Валидная форма изменения одного урока."""
    return {"type": "individual", "student_id": student_id,
            "starts_at": "2027-01-10T22:30", "duration_min": "60", **extra}


def messages():
    """Сохранённый журнал после HTTP-запроса."""
    with SessionLocal() as db:
        return db.scalars(select(SentMessage)).all()


def test_cancel_all_channels_and_no_repeat(client, owner, student_factory, lesson_factory, deliveries):
    student = student_factory(tutor_id=owner, timezone="Asia/Tokyo", remind_lesson=False)
    lesson = lesson_factory(student_id=student, starts_at=START, status="planned")
    bind(owner, student, ("telegram", "max"))
    for _ in range(2):
        response = client.post(f"/tutor/lessons/{lesson}", data=form(student, status="cancelled"), follow_redirects=False)
        assert response.status_code == 303
    assert len(deliveries) == 2
    assert {call[0] for call in deliveries} == {"telegram", "max"}
    assert all("11.01.2027 в 07:30" in call[2] and "отменён" in call[2] for call in deliveries)
    assert len(messages()) == 2
    assert all(message.status == "sent" for message in messages())


@pytest.mark.parametrize("drag", [False, True])
def test_move_old_and_new_time(client, owner, student_factory, lesson_factory, deliveries, drag):
    student = student_factory(tutor_id=owner, timezone="America/New_York")
    lesson = lesson_factory(student_id=student, starts_at=START, status="planned")
    bind(owner, student)
    url = f"/tutor/lessons/{lesson}"
    data = form(student, starts_at="2027-01-12T01:15")
    if drag:
        url += "/move"
        data = {"date": "2027-01-12", "time": "01:15"}
    for _ in range(2):
        assert client.post(url, data=data, follow_redirects=False).status_code == 303
    assert len(deliveries) == 1
    assert "10.01.2027 в 17:30" in deliveries[0][2]
    assert "11.01.2027 в 20:15" in deliveries[0][2]
    assert "перенесён" in deliveries[0][2]


@pytest.mark.parametrize("reason", ["disabled", "unbound", "other_field", "invalid"])
def test_no_notification(client, owner, student_factory, lesson_factory, deliveries, reason):
    student = student_factory(tutor_id=owner)
    lesson = lesson_factory(student_id=student, starts_at=START, status="planned")
    if reason != "unbound":
        bind(owner, student)
    if reason == "disabled":
        with SessionLocal() as db:
            save_settings(db, owner, {"notify_cancellation": False})
    data = form(student, status="cancelled")
    if reason == "other_field":
        data = form(student, note="Заметка", duration_min="90")
    if reason == "invalid":
        data["starts_at"] = "не дата"
    client.post(f"/tutor/lessons/{lesson}", data=data)
    assert deliveries == []
    assert messages() == []


@pytest.mark.parametrize("error", [SendError, RuntimeError])
def test_group_recipients_and_channel_failure(client, owner, student_factory, group_factory,
                                            group_member_factory, lesson_factory, deliveries, monkeypatch, error):
    group = group_factory(tutor_id=owner)
    students = [student_factory(tutor_id=owner, timezone=zone) for zone in ("UTC", "Asia/Tokyo", "UTC")]
    for student in students:
        group_member_factory(group_id=group, student_id=student)
    bind(owner, students[0], ("telegram", "max"))
    bind(owner, students[1])
    failures = []

    def fail(self, config, recipient, text):
        failures.append(recipient)
        raise error("Недоступен")

    monkeypatch.setattr(MaxSender, "send", fail)
    lesson = lesson_factory(group_id=group, type="group", starts_at=START, status="planned")
    data = form("", type="group", group_id=group, status="cancelled")
    assert client.post(f"/tutor/lessons/{lesson}", data=data, follow_redirects=False).status_code == 303
    assert len(deliveries) == 2
    assert len(failures) == (3 if error is SendError else 1)
    assert {message.status for message in messages()} == {"sent", "error"}
    assert len(messages()) == 3
    assert "10.01.2027 в 22:30" in deliveries[0][2]
    assert any("11.01.2027 в 07:30" in call[2] for call in deliveries)
    with SessionLocal() as db:
        assert db.get(Lesson, lesson).status == "cancelled"


def test_series_only_selected_lesson(client, owner, student_factory, lesson_factory, deliveries):
    student = student_factory(tutor_id=owner)
    bind(owner, student)
    with SessionLocal() as db:
        series = LessonSeries(slots=[], interval_weeks=1, until_date=date(2027, 2, 1))
        db.add(series)
        db.commit()
        series_id = series.id
    selected = lesson_factory(student_id=student, starts_at=START, series_id=series_id, status="planned")
    other = lesson_factory(student_id=student, starts_at=datetime(2027, 1, 17, 22, 30, tzinfo=UTC), series_id=series_id, status="planned")
    client.post(f"/tutor/lessons/{selected}", data=form(student, status="cancelled", series_all="1"))
    assert len(deliveries) == 1
    assert "последующ" not in deliveries[0][2]
    with SessionLocal() as db:
        assert db.get(Lesson, other).status == "planned"


@pytest.mark.parametrize("timezone", ["/Europe/Moscow", "../UTC", "Unknown/Zone"])
def test_invalid_student_timezone(client, owner, student_factory, lesson_factory, deliveries, timezone):
    student = student_factory(tutor_id=owner, timezone=timezone)
    lesson = lesson_factory(student_id=student, starts_at=START, status="planned")
    bind(owner, student)
    response = client.post(f"/tutor/lessons/{lesson}", data=form(student, status="cancelled"), follow_redirects=False)
    assert response.status_code == 303
    assert "10.01.2027 в 22:30" in deliveries[0][2]
    assert messages()[0].status == "sent"


@pytest.mark.parametrize("channel", ["telegram", "max"])
@pytest.mark.parametrize("drag", [False, True])
def test_transport_timeout_preserves_request(client, owner, student_factory, lesson_factory,
                                            monkeypatch, channel, drag):
    student = student_factory(tutor_id=owner)
    lesson = lesson_factory(student_id=student, starts_at=START, status="planned")
    bind(owner, student, ("telegram", "max"))
    attempts = []
    synced = []

    class Response:
        """Успешный ответ другого канала без выхода в сеть."""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true, "message": {"id": "1"}}'

    def urlopen(request, **kwargs):
        failed = ("api.telegram.org" in request.full_url) == (channel == "telegram")
        if failed:
            attempts.append(request.full_url)
            raise TimeoutError("read timed out")
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    view = "move" if drag else "update"
    monkeypatch.setattr(f"app.lesson.views.{view}.sync_lesson", lambda *args: synced.append(True))
    url = f"/tutor/lessons/{lesson}"
    data = form(student, status="cancelled")
    if drag:
        url += "/move"
        data = {"date": "2027-01-12", "time": "01:15"}
    response = client.post(url, data=data, follow_redirects=False)
    assert response.status_code == 303
    assert len(attempts) == 3
    assert synced == [True]
    journal = messages()
    assert len(journal) == 2
    assert {message.status for message in journal} == {"sent", "error"}
    with SessionLocal() as db:
        saved = db.get(Lesson, lesson)
        if drag:
            assert saved.starts_at == datetime(2027, 1, 12, 1, 15)
        else:
            assert saved.status == "cancelled"


def test_foreign_lesson_not_notified(client, owner, student_factory, lesson_factory, deliveries):
    student = student_factory()
    lesson = lesson_factory(student_id=student, starts_at=START, status="planned")
    bind(owner, student)
    assert client.post(f"/tutor/lessons/{lesson}", data=form(student, status="cancelled")).status_code == 404
    assert client.post(f"/tutor/lessons/{lesson}/move", data={"date": "2027-01-11", "time": "10:00"}).status_code == 404
    assert deliveries == []
