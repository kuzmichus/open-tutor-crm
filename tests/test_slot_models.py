"""Тесты модели окна для записи (спека slot-management, design.md D2).

Инварианты держатся в БД, а не только в форме (AGENTS.md, п. 10): окно с
длительностью вне закрытого списка или точный дубль «то же начало у того
же педагога» не должны сохраниться.
"""

from datetime import UTC, datetime

import pytest

from app.database import SessionLocal
from app.slot.models.slot import Slot



def _slot(tutor_id: str, **overrides) -> Slot:
    """Валидное окно: 14.10.2026 14:00 UTC, 40 минут, публичное."""
    values = {
        "tutor_id": tutor_id,
        "starts_at": datetime(2026, 10, 14, 14, 0, tzinfo=UTC),
        "duration_min": 40,
        "is_public": True,
    }
    values.update(overrides)
    return Slot(**values)


def test_slot_is_saved_with_uuid_and_timestamps(tutor_factory):
    """Окно сохраняется с uuid4-id, метками времени и своими полями."""
    tutor_id = tutor_factory()

    with SessionLocal() as session:
        slot = _slot(tutor_id)
        session.add(slot)
        session.commit()
        slot_id = slot.id

    assert len(slot_id) == 36
    with SessionLocal() as session:
        saved = session.get(Slot, slot_id)
        assert saved.tutor_id == tutor_id
        assert saved.duration_min == 40
        assert saved.is_public is True
        assert saved.created_at is not None
        assert saved.updated_at is not None


def test_slot_is_public_by_default(tutor_factory):
    """Признак публичности по умолчанию включён: окно создаётся для записи."""
    tutor_id = tutor_factory()
    with SessionLocal() as session:
        slot = Slot(
            tutor_id=tutor_id,
            starts_at=datetime(2026, 10, 14, 14, 0, tzinfo=UTC),
            duration_min=40,
        )
        session.add(slot)
        session.commit()
        assert slot.is_public is True


@pytest.mark.parametrize("duration", [0, 15, 25, 80, 200, -40])
def test_check_constraint_rejects_duration_outside_list(tutor_factory, duration, expect_integrity_error):
    """CHECK `ck_slots_duration` не пропускает длительность вне списка."""
    tutor_id = tutor_factory()
    with expect_integrity_error() as session:
        session.add(_slot(tutor_id, duration_min=duration))


def test_duplicate_tutor_start_is_rejected(tutor_factory, expect_integrity_error):
    """`UNIQUE(tutor_id, starts_at)` не даёт создать точный дубль окна."""
    tutor_id = tutor_factory()
    starts_at = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)

    with SessionLocal() as session:
        session.add(_slot(tutor_id, starts_at=starts_at))
        session.commit()

    with expect_integrity_error() as session:
        session.add(_slot(tutor_id, starts_at=starts_at, duration_min=60))


def test_same_start_for_different_tutors_is_allowed(tutor_factory):
    """У разных педагогов окна в одну минуту — легитимный случай."""
    first, second = tutor_factory(), tutor_factory()
    starts_at = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)

    with SessionLocal() as session:
        session.add_all(
            [
                _slot(first, starts_at=starts_at),
                _slot(second, starts_at=starts_at),
            ]
        )
        session.commit()


def test_slots_cascade_with_tutor(tutor_factory):
    """Удаление репетитора каскадом удаляет его окна (ondelete=CASCADE)."""
    from app.tutor.models.tutor import Tutor

    tutor_id = tutor_factory()
    with SessionLocal() as session:
        slot = _slot(tutor_id)
        session.add(slot)
        session.commit()
        slot_id = slot.id

    with SessionLocal() as session:
        session.delete(session.get(Tutor, tutor_id))
        session.commit()

    with SessionLocal() as session:
        assert session.get(Slot, slot_id) is None


def test_slot_table_is_registered_on_metadata():
    """Модель зарегистрирована в агрегаторе: таблица и её инварианты на месте."""
    from app.database import Base

    table = Base.metadata.tables["slots"]
    names = {constraint.name for constraint in table.constraints}
    assert "ck_slots_duration" in names
    assert "uq_slots_tutor_start" in names
