"""Тесты моделей уроков: таблицы, XOR-цель, CHECK-ограничения."""

from contextlib import contextmanager
from datetime import UTC, date, datetime

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.lesson.models.lesson import (
    LESSON_DURATIONS,
    Lesson,
)
from app.lesson.models.lesson_series import LessonSeries


@contextmanager
def _expect_integrity_error():
    """Контекст: `session.commit()` обязан упасть с IntegrityError.

    Используется для проверок CHECK-ограничений: запись с недопустимым
    значением не должна сохраниться.
    """
    with SessionLocal() as session:
        yield session
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return
    raise AssertionError("ожидался IntegrityError, но запись сохранилась")


def _starts_at() -> datetime:
    return datetime(2026, 10, 19, 10, 0, tzinfo=UTC)


def test_lesson_tables_are_created():
    """Таблицы `lessons` и `lesson_series` появились в базе (init_db/миграция)."""
    from sqlalchemy import inspect

    from app.database import engine

    tables = set(inspect(engine).get_table_names())
    assert {"lessons", "lesson_series"} <= tables


def test_lesson_series_is_saved_with_defaults(tutor_factory):
    """Серия получает uuid4-id, пустые слоты и интервал по умолчанию."""
    tutor_factory()

    with SessionLocal() as session:
        series = LessonSeries(until_date=date(2026, 11, 9))
        session.add(series)
        session.commit()
        series_id = series.id

    with SessionLocal() as session:
        saved = session.get(LessonSeries, series_id)
        assert len(saved.id) == 36
        assert saved.slots == []
        assert saved.interval_weeks == 1
        assert saved.until_date == date(2026, 11, 9)
        assert saved.created_at is not None
        assert saved.updated_at is not None


def test_individual_lesson_in_series_is_saved(tutor_factory, student_factory):
    """Обе записи создаются: серия + индивидуальный урок с учеником."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        series = LessonSeries(
            slots=[{"weekday": 0, "start_time": "10:00", "end_time": "11:00"}],
            interval_weeks=1,
            until_date=date(2026, 11, 9),
        )
        session.add(series)
        session.flush()
        lesson = Lesson(
            student_id=student_id,
            series_id=series.id,
            type="individual",
            starts_at=_starts_at(),
            duration_min=60,
            price=1200,
            note="Тема: квадратные уравнения",
            meeting_url="https://example.com/meet/1",
        )
        session.add(lesson)
        session.commit()
        lesson_id = lesson.id
        series_id = series.id

    with SessionLocal() as session:
        saved = session.get(Lesson, lesson_id)
        assert saved.student_id == student_id
        assert saved.group_id is None
        assert saved.series_id == series_id
        assert saved.type == "individual"
        # SQLite возвращает naive datetime (без зоны) — сравниваем без зоны.
        assert saved.starts_at == _starts_at().replace(tzinfo=None)
        assert saved.duration_min == 60
        assert saved.price == 1200
        # Значения по умолчанию: запланирован, без оценки и комментария.
        assert saved.status == "planned"
        assert saved.rating is None
        assert saved.family_comment is None
        assert saved.note == "Тема: квадратные уравнения"
        assert saved.meeting_url == "https://example.com/meet/1"


def test_group_lesson_targets_group(tutor_factory, group_factory):
    """Групповой урок ставится на группу, ученик не нужен."""
    tutor_id = tutor_factory()
    group_id = group_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        lesson = Lesson(
            group_id=group_id,
            type="group",
            starts_at=_starts_at(),
            duration_min=LESSON_DURATIONS[0],
        )
        session.add(lesson)
        session.commit()
        lesson_id = lesson.id

    with SessionLocal() as session:
        saved = session.get(Lesson, lesson_id)
        assert saved.group_id == group_id
        assert saved.student_id is None


def test_lesson_target_xor_is_enforced(tutor_factory, student_factory, group_factory):
    """Ровно одна цель: «обе» и «ни одной» нарушают XOR-проверку БД."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    group_id = group_factory(tutor_id=tutor_id)

    with _expect_integrity_error() as session:
        session.add(
            Lesson(
                student_id=student_id,
                group_id=group_id,
                starts_at=_starts_at(),
                duration_min=60,
            )
        )

    with _expect_integrity_error() as session:
        session.add(
            Lesson(
                starts_at=_starts_at(),
                duration_min=60,
            )
        )


def test_lesson_type_outside_list_is_rejected(tutor_factory, student_factory):
    """Тип вне закрытого списка (CHECK `ck_lessons_type`) не сохраняется."""
    student_id = student_factory(tutor_id=tutor_factory())

    with _expect_integrity_error() as session:
        session.add(
            Lesson(
                student_id=student_id,
                type="webinar",
                starts_at=_starts_at(),
                duration_min=60,
            )
        )


def test_lesson_duration_outside_list_is_rejected(tutor_factory, student_factory):
    """Длительность вне `LESSON_DURATIONS` (80 минут) не сохраняется."""
    student_id = student_factory(tutor_id=tutor_factory())

    with _expect_integrity_error() as session:
        session.add(
            Lesson(
                student_id=student_id,
                starts_at=_starts_at(),
                duration_min=80,
            )
        )


def test_lesson_status_and_rating_checks(tutor_factory, student_factory):
    """Статус вне planned/completed и оценка вне 1–5 не сохраняются."""
    student_id = student_factory(tutor_id=tutor_factory())

    with _expect_integrity_error() as session:
        session.add(
            Lesson(
                student_id=student_id,
                starts_at=_starts_at(),
                duration_min=60,
                status="cancelled",
            )
        )

    with _expect_integrity_error() as session:
        session.add(
            Lesson(
                student_id=student_id,
                starts_at=_starts_at(),
                duration_min=60,
                rating=6,
            )
        )


def test_lesson_boundary_values_are_saved(tutor_factory, student_factory):
    """Границы закрытых списков проходят: 30/180 минут, оценки 1 и 5."""
    student_id = student_factory(tutor_id=tutor_factory())

    saved_ids = []
    for duration, rating in ((30, 1), (180, 5)):
        with SessionLocal() as session:
            lesson = Lesson(
                student_id=student_id,
                starts_at=_starts_at(),
                duration_min=duration,
                rating=rating,
                status="completed",
            )
            session.add(lesson)
            session.commit()
            saved_ids.append(lesson.id)

    with SessionLocal() as session:
        assert session.get(Lesson, saved_ids[0]).duration_min == 30
        assert session.get(Lesson, saved_ids[1]).rating == 5


def test_deleting_series_cascades_lessons(tutor_factory, student_factory):
    """Удаление серии каскадом уносит её уроки (FK `series_id`)."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        series = LessonSeries(until_date=date(2026, 11, 9))
        session.add(series)
        session.flush()
        session.add(
            Lesson(
                student_id=student_id,
                series_id=series.id,
                starts_at=_starts_at(),
                duration_min=60,
            )
        )
        session.commit()
        series_id = series.id
        lesson_id = session.query(Lesson).one().id

    with SessionLocal() as session:
        session.delete(session.get(LessonSeries, series_id))
        session.commit()

    with SessionLocal() as session:
        assert session.get(Lesson, lesson_id) is None
