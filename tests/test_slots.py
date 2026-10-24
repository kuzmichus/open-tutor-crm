"""Тесты окон для записи: выборка недели, изоляция и вычисление занятости.

Занятость окна не хранится (design.md D4), поэтому проверяется тем, что
состояние меняется от данных: урок появляется и исчезает, бронь
подтверждается и отклоняется. Число запросов на рендер недели не должно
расти с числом окон (design.md Risks) — это отдельный тест через
`event.listen`.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.lesson.models.lesson import Lesson
from app.slot.models.slot import Slot
from app.slot.services.access import get_owned_slot
from app.slot.services.busy import (
    SLOT_BOOKED,
    SLOT_FREE,
    SLOT_LESSON,
    SLOT_PAST,
    SLOT_PENDING,
    slot_states,
)
from app.slot.services.slots import slots_between, week_slots

MONDAY = date(2026, 10, 12)


def _tutor(timezone: str = "UTC") -> SimpleNamespace:
    """Карточка репетитора для сервисов: нужна только её зона."""
    return SimpleNamespace(timezone=timezone)


def _utc(*args) -> datetime:
    """aware UTC из позиционных аргументов `datetime(...)`."""
    return datetime(*args, tzinfo=UTC)


def _slot(tutor_id: str, starts_at: datetime, duration_min: int = 40, **extra) -> Slot:
    """Окно в памяти (без коммита) — для чистых проверок состояния."""
    return Slot(
        tutor_id=tutor_id,
        starts_at=starts_at,
        duration_min=duration_min,
        **extra,
    )



def _save_lesson(tutor_id: str, student_id: str, starts_at: datetime, duration_min: int = 40) -> str:
    """Сохраняет урок напрямую в БД и возвращает его id."""
    with SessionLocal() as session:
        lesson = Lesson(
            student_id=student_id,
            type="individual",
            starts_at=starts_at,
            duration_min=duration_min,
            status="planned",
        )
        session.add(lesson)
        session.commit()
        return lesson.id



# --------------------------------------------------------------------------
# 2.1 Выборка недели и доступ к одной записи
# --------------------------------------------------------------------------


def test_week_slots_returns_only_own_slots_of_week(tutor_factory, slot_factory):
    """Окна недели: только этого репетитора и только в её границах."""
    owner, stranger = tutor_factory(), tutor_factory()
    slot_factory(owner, _utc(2026, 10, 12, 10, 0))
    slot_factory(owner, _utc(2026, 10, 18, 23, 0))     # воскресенье той же недели
    slot_factory(owner, _utc(2026, 10, 19, 10, 0))     # следующая неделя
    slot_factory(owner, _utc(2026, 10, 11, 10, 0))     # прошлая неделя
    slot_factory(stranger, _utc(2026, 10, 14, 10, 0))  # чужое окно

    with SessionLocal() as session:
        slots = week_slots(session, owner, MONDAY, _tutor())

    assert [slot.starts_at.replace(tzinfo=UTC) for slot in slots] == [
        _utc(2026, 10, 12, 10, 0),
        _utc(2026, 10, 18, 23, 0),
    ]


def test_week_slots_uses_tutor_zone_bounds(tutor_factory, slot_factory):
    """Границы недели считаются в зоне педагога, а не в UTC.

    Педагог в UTC+04: окно 12.10 00:30 его времени = 11.10 20:30 UTC —
    это его понедельник, и окно должно попасть в неделю с 12.10.
    """
    tutor_id = tutor_factory(timezone="Europe/Samara")
    slot_factory(tutor_id, _utc(2026, 10, 11, 20, 30))

    with SessionLocal() as session:
        slots = week_slots(session, tutor_id, MONDAY, _tutor("Europe/Samara"))

    assert len(slots) == 1


def test_slots_between_respects_half_open_interval(tutor_factory, slot_factory):
    """Интервал выборки — полуинтервал `[start, end)`."""
    tutor_id = tutor_factory()
    slot_factory(tutor_id, _utc(2026, 10, 12, 10, 0))
    slot_factory(tutor_id, _utc(2026, 10, 12, 12, 0))

    with SessionLocal() as session:
        slots = slots_between(
            session, tutor_id, _utc(2026, 10, 12, 10, 0), _utc(2026, 10, 12, 12, 0)
        )

    assert len(slots) == 1


def test_get_owned_slot_returns_own_slot(tutor_factory, slot_factory):
    """Своё окно доступно по id."""
    tutor_id = tutor_factory()
    slot_id = slot_factory(tutor_id, _utc(2026, 10, 14, 14, 0))

    with SessionLocal() as session:
        slot = get_owned_slot(session, slot_id, tutor_id)

    assert slot.id == slot_id


@pytest.mark.parametrize("missing", [False, True], ids=["чужое", "несуществующее"])
def test_get_owned_slot_hides_foreign_and_missing(tutor_factory, missing, slot_factory):
    """Чужое и несуществующее окно неразличимы: 404, не 403."""
    owner, stranger = tutor_factory(), tutor_factory()
    slot_id = "нет-такого-окна" if missing else slot_factory(
        stranger, _utc(2026, 10, 14, 14, 0)
    )

    with SessionLocal() as session:
        with pytest.raises(HTTPException) as error:
            get_owned_slot(session, slot_id, owner)

    assert error.value.status_code == 404


# --------------------------------------------------------------------------
# 2.2 Занятость: пересечение с уроками и активными бронями
# --------------------------------------------------------------------------


def test_free_slot_has_free_state(tutor_factory):
    """Окно без урока и брони в будущем — свободно."""
    tutor_id = tutor_factory()
    slot = _slot(tutor_id, _utc(2026, 10, 14, 14, 0))

    with SessionLocal() as session:
        states = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 12, 9, 0))

    assert states[slot.id] == SLOT_FREE


def test_partial_lesson_overlap_makes_slot_busy(tutor_factory, student_factory):
    """Частичное пересечение (14:00–14:40 и 14:20–15:00) — окно занято уроком."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    slot = _slot(tutor_id, _utc(2026, 10, 14, 14, 0))
    _save_lesson(tutor_id, student_id, _utc(2026, 10, 14, 14, 20), 40)

    with SessionLocal() as session:
        states = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 12, 9, 0))

    assert states[slot.id] == SLOT_LESSON


def test_touching_lesson_does_not_make_slot_busy(tutor_factory, student_factory):
    """Полуинтервалы: урок сразу после окна занятостью не является."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    slot = _slot(tutor_id, _utc(2026, 10, 14, 14, 0))
    _save_lesson(tutor_id, student_id, _utc(2026, 10, 14, 14, 40), 40)

    with SessionLocal() as session:
        states = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 12, 9, 0))

    assert states[slot.id] == SLOT_FREE


def test_past_slot_with_confirmed_booking_shows_booking(tutor_factory, slot_factory, booking_factory):
    """Приоритет: окно в прошлом с подтверждённой бронью — «занято записью»."""
    tutor_id = tutor_factory()
    slot_id = slot_factory(tutor_id, _utc(2026, 10, 12, 10, 0))
    booking_factory(slot_id, status="confirmed")

    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        states = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 20, 9, 0))

    assert states[slot_id] == SLOT_BOOKED


def test_pending_booking_has_pending_state(tutor_factory, slot_factory, booking_factory):
    """Ожидающая бронь — отдельное состояние, не «занято записью»."""
    tutor_id = tutor_factory()
    slot_id = slot_factory(tutor_id, _utc(2026, 10, 14, 10, 0))
    booking_factory(slot_id, status="pending")

    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        states = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 12, 9, 0))

    assert states[slot_id] == SLOT_PENDING


def test_rejected_booking_frees_slot(tutor_factory, slot_factory, booking_factory):
    """Завершающая бронь окно не занимает: после `reject` оно свободно."""
    tutor_id = tutor_factory()
    slot_id = slot_factory(tutor_id, _utc(2026, 10, 14, 10, 0))
    booking_factory(slot_id, status="rejected")

    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        states = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 12, 9, 0))

    assert states[slot_id] == SLOT_FREE


def test_past_slot_without_busy_data_shows_past(tutor_factory):
    """Окно, чьё время прошло и нет брони/урока, — «время прошло»."""
    tutor_id = tutor_factory()
    slot = _slot(tutor_id, _utc(2026, 10, 12, 10, 0))

    with SessionLocal() as session:
        states = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 20, 9, 0))

    assert states[slot.id] == SLOT_PAST


def test_lesson_in_past_wins_over_past_state(tutor_factory, student_factory):
    """Приоритет `lesson > past`: прошедшее окно с уроком — «занято уроком»."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    slot = _slot(tutor_id, _utc(2026, 10, 12, 10, 0))
    _save_lesson(tutor_id, student_id, _utc(2026, 10, 12, 10, 0), 40)

    with SessionLocal() as session:
        states = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 20, 9, 0))

    assert states[slot.id] == SLOT_LESSON


def test_deleting_lesson_returns_slot_to_free(tutor_factory, student_factory, slot_factory):
    """Удаление урока возвращает окно в свободные без отдельного действия."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    slot_id = slot_factory(tutor_id, _utc(2026, 10, 14, 14, 0))
    lesson_id = _save_lesson(tutor_id, student_id, _utc(2026, 10, 14, 14, 0), 40)

    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        before = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 12, 9, 0))

    with SessionLocal() as session:
        session.delete(session.get(Lesson, lesson_id))
        session.commit()

    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        after = slot_states(session, tutor_id, [slot], now=_utc(2026, 10, 12, 9, 0))

    assert before[slot_id] == SLOT_LESSON
    assert after[slot_id] == SLOT_FREE


def test_foreign_lesson_does_not_busy_slot(tutor_factory, student_factory):
    """Урок другого репетитора в то же время окно не занимает."""
    owner, stranger = tutor_factory(), tutor_factory()
    stranger_student = student_factory(tutor_id=stranger)
    slot = _slot(owner, _utc(2026, 10, 14, 14, 0))
    _save_lesson(stranger, stranger_student, _utc(2026, 10, 14, 14, 0), 40)

    with SessionLocal() as session:
        states = slot_states(session, owner, [slot], now=_utc(2026, 10, 12, 9, 0))

    assert states[slot.id] == SLOT_FREE


def test_slot_states_returns_empty_for_no_slots(tutor_factory):
    """Пустой список окон — пустой словарь состояний, без запросов."""
    tutor_id = tutor_factory()
    with SessionLocal() as session:
        assert slot_states(session, tutor_id, [], now=_utc(2026, 10, 12, 9, 0)) == {}


# --------------------------------------------------------------------------
# 2.3 Нет N+1: число запросов не растёт с числом окон
# --------------------------------------------------------------------------


def _count_queries(action) -> int:
    """Считает SQL-запросы, выполненные `action`."""
    counter = {"count": 0}

    def _on_execute(*args, **kwargs):
        counter["count"] += 1

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)
    return counter["count"]


def test_slot_states_query_count_does_not_grow_with_slots(
    tutor_factory, student_factory
, slot_factory):
    """Один и десять окон дают одинаковое число запросов (нет N+1)."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    _save_lesson(tutor_id, student_id, _utc(2026, 10, 14, 14, 0), 40)

    one_id = slot_factory(tutor_id, _utc(2026, 10, 14, 16, 0))
    with SessionLocal() as session:
        one = [session.get(Slot, one_id)]
        one_count = _count_queries(
            lambda: slot_states(session, tutor_id, one, now=_utc(2026, 10, 12, 9, 0))
        )

    # Десять окон: пять до урока и пять после, часть пересекается с уроком.
    many_ids = [
        slot_factory(tutor_id, _utc(2026, 10, 14, 9, 0) + timedelta(minutes=20 * i))
        for i in range(10)
    ]
    with SessionLocal() as session:
        many = [session.get(Slot, slot_id) for slot_id in many_ids]
        many_count = _count_queries(
            lambda: slot_states(session, tutor_id, many, now=_utc(2026, 10, 12, 9, 0))
        )

    assert many_count == one_count, (
        f"запросов на десять окон {many_count}, на одно {one_count}: появился N+1"
    )
