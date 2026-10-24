"""Миграция сдвига данных в UTC: инвариант «отображение не изменилось».

Схема до и после миграции не меняется, поэтому база создаётся обычным
`create_all`, а сама ревизия вызывается на копии in-memory базы через
`MigrationContext`/`Operations` — без обращения к рабочему файлу БД.
Зона-источник фиксируется `MIGRATION_SOURCE_TZ`, чтобы тесты не зависели
от настройки машины (design D8).
"""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.common.services.tutor_time import to_local
from app.database import SessionLocal, engine
from app.homework.models.homework import Homework
from app.lesson.models.lesson import Lesson
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import as_utc

# Зона-источник теста: UTC+04 — та же, что в рабочей базе проекта.
SOURCE_TZ = "Europe/Ulyanovsk"
# Наивное настенное значение до миграции: «22.10.2026 10:15» в зоне-источнике.
WALL_LESSON = datetime(2026, 10, 22, 10, 15)
WALL_HOMEWORK = datetime(2026, 10, 25, 18, 0)
# Результат сдвига: те же моменты в UTC.
UTC_LESSON = datetime(2026, 10, 22, 6, 15, tzinfo=UTC)
UTC_HOMEWORK = datetime(2026, 10, 25, 14, 0, tzinfo=UTC)

_REVISION_FILE = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "510599ec7624_store_datetimes_in_utc.py"
)


@pytest.fixture()
def source_zone(monkeypatch):
    """Фиксирует зону-источник: тесты не зависят от настройки машины."""
    monkeypatch.setenv("MIGRATION_SOURCE_TZ", SOURCE_TZ)


@pytest.fixture()
def migration():
    """Модуль ревизии, загруженный по файлу: `alembic/versions/` — не пакет."""
    spec = importlib.util.spec_from_file_location(
        "store_datetimes_in_utc", _REVISION_FILE
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(migration, fn_name: str) -> None:
    """Вызывает upgrade/downgrade ревизии на тестовом соединении."""
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            getattr(migration, fn_name)()


def _seed(tutor_factory, student_factory) -> tuple[str, str]:
    """Тьютор с NULL-зоной, ученик, урок и ДЗ с наивным настенным временем."""
    tutor_id = tutor_factory(timezone=None)
    student_id = student_factory(tutor_id=tutor_id)
    with SessionLocal() as session:
        lesson = Lesson(
            student_id=student_id,
            type="individual",
            starts_at=WALL_LESSON,
            duration_min=40,
        )
        session.add(lesson)
        session.flush()
        session.add(
            Homework(
                lesson_id=lesson.id,
                assignment="Учебник, стр. 12",
                due_at=WALL_HOMEWORK,
            )
        )
        lesson_id = lesson.id
        session.commit()
        return tutor_id, lesson_id


def _snapshot(tutor_id: str, lesson_id: str) -> tuple:
    """Значения до/после миграции в одном представлении для сравнения."""
    with SessionLocal() as session:
        lesson = session.get(Lesson, lesson_id)
        homework = (
            session.query(Homework).filter_by(lesson_id=lesson_id).one()
        )
        tutor = session.get(Tutor, tutor_id)
        return (
            as_utc(lesson.starts_at),
            as_utc(homework.due_at),
            tutor.timezone,
        )


def test_upgrade_shifts_wall_time_to_utc(
    migration, source_zone, tutor_factory, student_factory
):
    """«22.10.2026 10:15» после миграции — 06:15 UTC, показ — 10:15."""
    tutor_id, lesson_id = _seed(tutor_factory, student_factory)
    _run(migration, "upgrade")

    starts_at, due_at, timezone = _snapshot(tutor_id, lesson_id)
    assert starts_at == UTC_LESSON
    assert due_at == UTC_HOMEWORK
    # Зона-источник записана в карточку репетитора (для показа и бейджа).
    assert timezone == SOURCE_TZ

    # Отображение не изменилось: 06:15 UTC читается как 10:15 местного.
    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        lesson = session.get(Lesson, lesson_id)
        local = to_local(lesson.starts_at, tutor)
    assert local.strftime("%Y-%m-%dT%H:%M") == "2026-10-22T10:15"
    assert local.strftime("%d.%m.%Y, %H:%M") == "22.10.2026, 10:15"


def test_downgrade_restores_wall_time_and_clears_zone(
    migration, source_zone, tutor_factory, student_factory
):
    """Downgrade возвращает настенное время зоны-источника и NULL-зону."""
    tutor_id, lesson_id = _seed(tutor_factory, student_factory)
    _run(migration, "upgrade")
    _run(migration, "downgrade")

    with SessionLocal() as session:
        lesson = session.get(Lesson, lesson_id)
        homework = session.query(Homework).filter_by(lesson_id=lesson_id).one()
        tutor = session.get(Tutor, tutor_id)
        assert lesson.starts_at.replace(tzinfo=None) == WALL_LESSON
        assert homework.due_at.replace(tzinfo=None) == WALL_HOMEWORK
        assert tutor.timezone is None


def test_upgrade_after_downgrade_matches_single_upgrade(
    migration, source_zone, tutor_factory, student_factory
):
    """upgrade → downgrade → upgrade даёт те же значения, что один upgrade."""
    tutor_id, lesson_id = _seed(tutor_factory, student_factory)
    _run(migration, "upgrade")
    once = _snapshot(tutor_id, lesson_id)

    _run(migration, "downgrade")
    _run(migration, "upgrade")
    twice = _snapshot(tutor_id, lesson_id)

    assert twice == once
    assert twice == (UTC_LESSON, UTC_HOMEWORK, SOURCE_TZ)


def test_zone_source_is_printed_to_log(migration, source_zone, capsys):
    """Зона-источник печатается в лог — результат сдвига воспроизводим."""
    _run(migration, "upgrade")
    assert f"зона-источник сдвига: {SOURCE_TZ}" in capsys.readouterr().out
