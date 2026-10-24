"""Тесты модели брони (спека booking-management, design.md D3).

Инварианты держатся в БД: статус вне закрытого списка не сохраняется,
активная бронь на окно может быть только одна (частичный уникальный
индекс), удаление окна каскадно уносит брони, а удаление ученика оставляет
бронь с `student_id = NULL` (история заявки не теряется).
"""

from datetime import UTC, datetime

import pytest

from app.booking.models.booking import (
    ACTIVE_BOOKING_STATUSES,
    BOOKING_STATUSES,
    BOOKING_STATUS_LABELS,
    Booking,
)
from app.database import SessionLocal
from app.slot.models.slot import Slot



def _slot(tutor_id: str, **overrides) -> Slot:
    """Валидное окно: 14.10.2026 14:00 UTC, 40 минут."""
    values = {
        "tutor_id": tutor_id,
        "starts_at": datetime(2026, 10, 14, 14, 0, tzinfo=UTC),
        "duration_min": 40,
        "is_public": True,
    }
    values.update(overrides)
    return Slot(**values)


def _booking(slot_id: str, **overrides) -> Booking:
    """Валидная заявка: имя, контакт, статус «Ожидает подтверждения»."""
    values = {
        "slot_id": slot_id,
        "name": "Иван Иванов",
        "contact": "+7 916 000-00-00",
        "status": "pending",
    }
    values.update(overrides)
    return Booking(**values)


def _slot_id(tutor_id: str, **overrides) -> str:
    """Сохраняет окно и возвращает его id (бронь ссылается на окно)."""
    with SessionLocal() as session:
        slot = _slot(tutor_id, **overrides)
        session.add(slot)
        session.commit()
        return slot.id


def test_constants_match_closed_lists():
    """Закрытые списки и подписи — один источник истины для CHECK и селектов."""
    assert BOOKING_STATUSES == ("pending", "confirmed", "rejected", "cancelled")
    assert ACTIVE_BOOKING_STATUSES == ("pending", "confirmed")
    assert set(BOOKING_STATUS_LABELS) == set(BOOKING_STATUSES)


def test_booking_is_saved_with_uuid_and_timestamps(tutor_factory):
    """Бронь сохраняется с uuid4-id и `created_at`; `decided_at` пуст."""
    tutor_id = tutor_factory()
    slot_id = _slot_id(tutor_id)

    with SessionLocal() as session:
        booking = _booking(slot_id)
        session.add(booking)
        session.commit()
        booking_id = booking.id

    assert len(booking_id) == 36
    with SessionLocal() as session:
        saved = session.get(Booking, booking_id)
        assert saved.slot_id == slot_id
        assert saved.name == "Иван Иванов"
        assert saved.status == "pending"
        assert saved.student_id is None
        assert saved.lesson_id is None
        assert saved.created_at is not None
        assert saved.decided_at is None


@pytest.mark.parametrize("status", ["waiting", "done", "", "PENDING"])
def test_status_outside_list_is_rejected(tutor_factory, status, expect_integrity_error):
    """CHECK `ck_bookings_status` не пропускает статус вне закрытого списка."""
    tutor_id = tutor_factory()
    slot_id = _slot_id(tutor_id)
    with expect_integrity_error() as session:
        session.add(_booking(slot_id, status=status))


def test_second_active_booking_is_rejected(tutor_factory, expect_integrity_error):
    """Частичный уникальный индекс: две активные брони на окно невозможны."""
    tutor_id = tutor_factory()
    slot_id = _slot_id(tutor_id)

    with SessionLocal() as session:
        session.add(_booking(slot_id))
        session.commit()

    with expect_integrity_error() as session:
        session.add(_booking(slot_id, name="Пётр Петров"))


def test_second_booking_allowed_after_reject(tutor_factory):
    """После перевода первой брони в `rejected` окно принимает новую заявку."""
    tutor_id = tutor_factory()
    slot_id = _slot_id(tutor_id)

    with SessionLocal() as session:
        first = _booking(slot_id)
        session.add(first)
        session.commit()
        first.status = "rejected"
        first.decided_at = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
        session.commit()

    with SessionLocal() as session:
        session.add(_booking(slot_id, name="Пётр Петров"))
        session.commit()
        statuses = sorted(
            booking.status
            for booking in session.query(Booking).filter_by(slot_id=slot_id)
        )

    assert statuses == ["pending", "rejected"]


def test_completed_statuses_do_not_conflict(tutor_factory):
    """Завершающие брони на одно окно живут рядом: индекс смотрит только активные."""
    tutor_id = tutor_factory()
    slot_id = _slot_id(tutor_id)

    with SessionLocal() as session:
        session.add_all(
            [
                _booking(slot_id, status="rejected"),
                _booking(slot_id, status="cancelled"),
            ]
        )
        session.commit()


def test_bookings_cascade_with_slot(tutor_factory):
    """Удаление окна каскадом удаляет брони: бронь без окна бессмысленна."""
    tutor_id = tutor_factory()
    slot_id = _slot_id(tutor_id)

    with SessionLocal() as session:
        booking = _booking(slot_id)
        session.add(booking)
        session.commit()
        booking_id = booking.id

    with SessionLocal() as session:
        session.delete(session.get(Slot, slot_id))
        session.commit()

    with SessionLocal() as session:
        assert session.get(Booking, booking_id) is None


def test_student_delete_keeps_booking_with_null_student(tutor_factory, student_factory):
    """Удаление ученика оставляет бронь с `student_id = NULL` (SET NULL)."""
    from app.student.models.student import Student

    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    slot_id = _slot_id(tutor_id)

    with SessionLocal() as session:
        booking = _booking(slot_id, status="confirmed", student_id=student_id)
        session.add(booking)
        session.commit()
        booking_id = booking.id

    with SessionLocal() as session:
        session.delete(session.get(Student, student_id))
        session.commit()

    with SessionLocal() as session:
        saved = session.get(Booking, booking_id)
        assert saved is not None, "история заявки не должна исчезать"
        assert saved.student_id is None


def test_booking_table_is_registered_on_metadata():
    """Таблица, CHECK и частичный уникальный индекс объявлены в модели."""
    from app.database import Base

    table = Base.metadata.tables["bookings"]
    names = {constraint.name for constraint in table.constraints}
    assert "ck_bookings_status" in names

    index = next(i for i in table.indexes if i.name == "ux_bookings_active_slot")
    assert index.unique
    where = str(index.dialect_options["sqlite"]["where"])
    assert "pending" in where and "confirmed" in where
