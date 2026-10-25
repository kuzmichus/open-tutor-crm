"""Runner cron (`app/common/services/cron.py`) и точка входа `cron.py`.

Runner выполняется с тестовой БД (conftest): реальное задание
автозавершения коммитится, падение одного задания откатывает только его
и не мешает остальным; код возврата сигнализирует о падении. `import cron`
проверяет саму точку входа (pythonpath = ["."]).
"""

import cron  # noqa: F401  # точка входа импортируется и не падает
from datetime import timedelta

from app.common.services import cron as cron_module
from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.services.clock import utcnow

PASSWORD = "Секретный-Пароль-1"


def test_registry_contains_auto_complete():
    """В реестре зарегистрировано задание автозавершения уроков."""
    names = [name for name, _ in cron_module.TASKS]
    assert "lesson.auto_complete" in names


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


def test_cron_entry_point_wiring():
    """`cron.py` — тонкая обёртка: берёт `run_tasks` из общего модуля."""
    import inspect

    source = inspect.getsource(cron)
    assert "from app.common.services.cron import run_tasks" in source
    assert cron.run_tasks is cron_module.run_tasks
