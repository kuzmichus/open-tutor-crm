"""Runner cron (`app/common/services/cron.py`) и точка входа `cron.py`.

Runner выполняется с тестовой БД (conftest): реальное задание
автозавершения коммитится, падение одного задания откатывает только его
и не мешает остальным; код возврата сигнализирует о падении. `import cron`
проверяет саму точку входа (pythonpath = ["."]).
"""

import urllib.request
from datetime import date, timedelta

import cron  # noqa: F401  # точка входа импортируется и не падает

from app.common.services import cron as cron_module
from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.messenger.models.sent_message import SentMessage
from app.messenger.services.binding import chat_id_key
from app.messenger.services.birthday_digest import BIRTHDAY_SENT_KEY
from app.messenger.services.messengers import token_key
from app.student.models.student import Student
from app.tutor.services.clock import utcnow
from app.tutor.services.params import get_param, set_param

PASSWORD = "Секретный-Пароль-1"
TELEGRAM_TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"


def test_registry_contains_auto_complete():
    """В реестре зарегистрировано задание автозавершения уроков."""
    names = [name for name, _ in cron_module.TASKS]
    assert "lesson.auto_complete" in names

def test_registry_contains_daily_digest():
    """В реестре зарегистрировано задание дневной сводки в мессенджеры."""
    names = [name for name, _ in cron_module.TASKS]
    assert "messenger.daily_digest" in names

def test_registry_contains_birthday_digest():
    """В реестре зарегистрировано задание рассылки дней рождения."""
    names = [name for name, _ in cron_module.TASKS]
    assert "messenger.birthday_digest" in names


def test_run_tasks_commits_changes(tutor_factory, student_factory, lesson_factory):
    """Прогон runner'а завершает просроченный урок и коммитит изменение."""
    student_id = student_factory()
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() - timedelta(hours=25),
        price=1200,
    )

    assert cron_module.run_tasks() == 0

    with SessionLocal() as db:
        assert db.get(Lesson, lesson_id).status == "completed"


def test_failing_task_isolated(monkeypatch, tutor_factory):
    """Упавшее задание откатывается, остальные выполняются и коммитятся."""
    tutor_id = tutor_factory()
    calls: list[str] = []

    def ok(db):
        """Коммитимое задание: добавляет ученика."""
        calls.append("ok")
        db.add(Student(tutor_id=tutor_id, first_name="Успешный", kind="child"))
        return 1

    def boom(db):
        """Падающее задание: успевает добавить ученика до исключения."""
        calls.append("boom")
        db.add(Student(tutor_id=tutor_id, first_name="Откаченный", kind="child"))
        raise RuntimeError("упавшее задание")

    monkeypatch.setattr(cron_module, "TASKS", [("ok", ok), ("boom", boom)])
    assert cron_module.run_tasks() == 1
    assert calls == ["ok", "boom"]  # падение «boom» не остановило «ok»

    with SessionLocal() as db:
        names = {row.first_name for row in db.query(Student).all()}
    assert "Успешный" in names      # задание закоммичено
    assert "Откаченный" not in names  # упавшее откатилось


def test_run_tasks_commits_birthday_digest(monkeypatch, tutor_factory, student_factory):
    """Прогон runner'а коммитит и маркер дня, и журнал отправки."""
    from datetime import UTC, datetime

    from app.messenger.services import birthday_digest

    calls: list[str] = []

    class _Response:
        """Минимальный ответ urlopen: контекстный менеджер с JSON-телом."""

        def read(self):
            return b'{"ok": true, "result": {"message_id": 1}}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None, context=None):
        calls.append(request.full_url)
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    # «Сейчас» задания подменяется: прогон не должен зависеть от часов машины.
    monkeypatch.setattr(
        birthday_digest, "utcnow", lambda: datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    )
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    with SessionLocal() as db:
        set_param(db, tutor_id, token_key("telegram"), TELEGRAM_TOKEN)
        set_param(db, tutor_id, chat_id_key("telegram"), "100200300")

    assert cron_module.run_tasks() == 0

    assert len(calls) == 1
    with SessionLocal() as db:
        assert get_param(db, tutor_id, BIRTHDAY_SENT_KEY) == "2026-11-02"
        assert db.query(SentMessage).filter_by(tutor_id=tutor_id).count() == 1


def test_cron_entry_point_wiring():
    """`cron.py` — тонкая обёртка: берёт `run_tasks` из общего модуля."""
    import inspect

    source = inspect.getsource(cron)
    assert "from app.common.services.cron import run_tasks" in source
    assert cron.run_tasks is cron_module.run_tasks
