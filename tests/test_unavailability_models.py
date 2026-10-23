"""Тесты модели недоступности: дефолты, CHECK-ограничения режимов, каскад.

Инварианты держатся в БД, а не только в форме (AGENTS.md, п. 10): запись
с полями чужого режима, с причиной вне списка или с последним днём раньше
первого не должна сохраниться.
"""

from contextlib import contextmanager
from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.unavailability.models.unavailability import (
    DAYOFF_REASON,
    PERIOD_REASONS,
    REASON_LABELS,
    UNAVAILABILITY_MODES,
    WEEKDAY_LABELS,
    TutorUnavailability,
)


@contextmanager
def _expect_integrity_error():
    """Контекст: `session.commit()` обязан упасть с IntegrityError.

    Используется для проверок CHECK-ограничений: запись с недопустимым
    значением не должна сохраниться (паттерн `test_lesson_models.py`).
    """
    with SessionLocal() as session:
        yield session
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return
    raise AssertionError("ожидался IntegrityError, но запись сохранилась")


def _period(tutor_id: str, **overrides) -> TutorUnavailability:
    """Валидная отметка периода: отпуск 26.10–30.10.2026."""
    values = {
        "tutor_id": tutor_id,
        "mode": "period",
        "reason": "vacation",
        "start_date": date(2026, 10, 26),
        "end_date": date(2026, 10, 30),
    }
    values.update(overrides)
    return TutorUnavailability(**values)


def _weekday(tutor_id: str, **overrides) -> TutorUnavailability:
    """Валидный постоянный выходной: суббота без ограничения срока."""
    values = {
        "tutor_id": tutor_id,
        "mode": "weekday",
        "reason": DAYOFF_REASON,
        "weekday": 5,
    }
    values.update(overrides)
    return TutorUnavailability(**values)


def test_constants_match_closed_lists():
    """Закрытые списки и подписи — один источник истины для CHECK и селектов."""
    assert UNAVAILABILITY_MODES == ("period", "weekday")
    assert PERIOD_REASONS == ("vacation", "sick", "unavailable")
    assert DAYOFF_REASON == "dayoff"
    # Каждая причина имеет подпись, лишних подписей нет.
    assert set(REASON_LABELS) == set(PERIOD_REASONS) | {DAYOFF_REASON}
    assert WEEKDAY_LABELS == ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        (
            _period,
            {
                "mode": "period",
                "reason": "vacation",
                "start_date": date(2026, 10, 26),
                "end_date": date(2026, 10, 30),
                "weekday": None,
                "until_date": None,
            },
        ),
        (
            _weekday,
            {
                "mode": "weekday",
                "reason": DAYOFF_REASON,
                "weekday": 5,
                "until_date": None,
                "start_date": None,
                "end_date": None,
            },
        ),
    ],
    ids=["period", "weekday"],
)
def test_mark_is_saved_with_uuid_and_timestamps(tutor_factory, build, expected):
    """Обе отметки сохраняются с uuid4-id, метками времени и своими полями."""
    tutor_id = tutor_factory()

    with SessionLocal() as session:
        mark = build(tutor_id)
        session.add(mark)
        session.commit()
        mark_id = mark.id

    assert len(mark_id) == 36
    with SessionLocal() as session:
        saved = session.get(TutorUnavailability, mark_id)
        for field, value in expected.items():
            assert getattr(saved, field) == value, field
        assert saved.created_at is not None
        assert saved.updated_at is not None


@pytest.mark.parametrize(
    ("build", "overrides"),
    [
        # Период без первого дня (CHECK ck_unavailability_period).
        (_period, {"start_date": None}),
        # Выходной без дня недели (CHECK ck_unavailability_weekday).
        (_weekday, {"weekday": None}),
        # Причина вне закрытого списка.
        (_period, {"reason": "holiday"}),
        # У постоянного выходного причина — только «Выходной».
        (_weekday, {"reason": "vacation"}),
        # Последний день раньше первого.
        (
            _period,
            {"start_date": date(2026, 10, 30), "end_date": date(2026, 10, 26)},
        ),
        # Режимы не смешиваются: период с полем выходного.
        (_period, {"weekday": 3}),
        # День недели вне 0–6.
        (_weekday, {"weekday": 7}),
        # Выходной с датами периода.
        (_weekday, {"start_date": date(2026, 10, 26)}),
    ],
    ids=[
        "period-without-start",
        "weekday-without-weekday",
        "period-reason-not-in-list",
        "weekday-not-dayoff-reason",
        "period-end-before-start",
        "period-with-weekday-field",
        "weekday-out-of-range",
        "weekday-with-period-dates",
    ],
)
def test_check_constraints_reject_invalid_rows(tutor_factory, build, overrides):
    """Недопустимая комбинация полей не сохраняется: CHECK'и режимов в БД."""
    tutor_id = tutor_factory()

    with _expect_integrity_error() as session:
        session.add(build(tutor_id, **overrides))


def test_marks_cascade_with_tutor(tutor_factory):
    """Удаление репетитора каскадом удаляет его отметки (ondelete=CASCADE)."""
    from app.tutor.models.tutor import Tutor

    tutor_id = tutor_factory()
    with SessionLocal() as session:
        mark = _period(tutor_id)
        session.add(mark)
        session.commit()
        mark_id = mark.id

    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        session.delete(tutor)
        session.commit()

    with SessionLocal() as session:
        assert session.get(TutorUnavailability, mark_id) is None


def test_unavailability_table_is_registered_on_metadata():
    """Модель зарегистрирована в агрегаторе: таблица есть в `Base.metadata`.

    Без импорта в `app/models.py` autogenerate Alembic не увидел бы
    таблицу и не создал бы миграцию (AGENTS.md: агрегатор моделей).
    Оба CHECK-ограничения режимов объявлены на той же таблице.
    """
    from app.database import Base

    table = Base.metadata.tables["tutor_unavailability"]
    names = {constraint.name for constraint in table.constraints}
    assert {"ck_unavailability_period", "ck_unavailability_weekday"} <= names


def test_updated_at_changes_on_update(tutor_factory):
    """`updated_at` обновляется при изменении срока отметки."""
    tutor_id = tutor_factory()
    with SessionLocal() as session:
        mark = _period(tutor_id)
        session.add(mark)
        session.commit()
        mark_id = mark.id

    with SessionLocal() as session:
        saved = session.get(TutorUnavailability, mark_id)
        created = saved.created_at
        saved.end_date = date(2026, 11, 6)
        session.commit()

    with SessionLocal() as session:
        saved = session.get(TutorUnavailability, mark_id)
        assert saved.end_date == date(2026, 11, 6)
        assert isinstance(saved.updated_at, datetime)
        # SQLite теряет tzinfo — сравниваем значения без зоны. Строгое «>»:
        # метка обязана сдвинуться, «>=» проходил бы и без onupdate.
        assert saved.updated_at.replace(tzinfo=None) > created.replace(tzinfo=None)
