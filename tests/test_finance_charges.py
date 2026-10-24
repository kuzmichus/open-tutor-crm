"""Тесты списаний за уроки: индивидуальные, групповые, идемпотентность.

Проверяется `sync_lesson_charge` — единственная точка, где урок становится
операцией счёта (design D6). Функция не коммитит: тесты делают это сами,
как это делает вызывающий путь записи урока.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import balance
from app.finance.services.charges import lesson_targets, sync_lesson_charge
from app.lesson.models.lesson import Lesson


def _lesson(session, *, student_id=None, group_id=None, price=1200, status="completed", starts_at=None) -> Lesson:
    """Урок напрямую в БД (без списаний — их создаёт только sync)."""
    lesson = Lesson(
        student_id=student_id,
        group_id=group_id,
        type="group" if group_id else "individual",
        starts_at=starts_at or datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
        duration_min=60,
        price=price,
        status=status,
    )
    session.add(lesson)
    session.commit()
    return lesson


def _charges(session, lesson_id: str) -> list[AccountOperation]:
    """Списания урока (только `kind='lesson'`)."""
    return list(
        session.scalars(
            select(AccountOperation).where(
                AccountOperation.lesson_id == lesson_id,
                AccountOperation.kind == "lesson",
            )
        ).all()
    )


# --------------------------------------------------------------------------
# Индивидуальный урок
# --------------------------------------------------------------------------


def test_completed_individual_lesson_creates_charge(student_factory):
    """Проведённый урок 1200 создаёт списание и уменьшает баланс."""
    student_id = student_factory()

    with SessionLocal() as session:
        lesson = _lesson(session, student_id=student_id, price=1200)

        assert sync_lesson_charge(session, lesson) == 1
        session.commit()

        charges = _charges(session, lesson.id)
        assert len(charges) == 1
        assert charges[0].student_id == student_id
        assert charges[0].amount == 1200
        assert charges[0].status is None
        assert charges[0].method is None
        assert balance(session, student_id) == -1200


def test_planned_lesson_creates_no_charge(student_factory):
    """«Запланирован» — занятие не состоялось, списания нет."""
    student_id = student_factory()

    with SessionLocal() as session:
        lesson = _lesson(session, student_id=student_id, status="planned")

        assert sync_lesson_charge(session, lesson) == 0
        session.commit()

        assert _charges(session, lesson.id) == []
        assert balance(session, student_id) == 0


def test_lesson_without_price_creates_no_charge(student_factory):
    """Урок без цены не списывает ничего — строки нет вовсе, а не «0 ₽»."""
    student_id = student_factory()

    with SessionLocal() as session:
        lesson = _lesson(session, student_id=student_id, price=None)

        assert sync_lesson_charge(session, lesson) == 0
        session.commit()

        assert _charges(session, lesson.id) == []
        assert balance(session, student_id) == 0


def test_returning_to_planned_removes_charge(student_factory):
    """Возврат в «Запланирован» снимает списание и возвращает баланс."""
    student_id = student_factory()

    with SessionLocal() as session:
        lesson = _lesson(session, student_id=student_id, price=1200)
        sync_lesson_charge(session, lesson)
        session.commit()
        assert balance(session, student_id) == -1200

        lesson.status = "planned"
        sync_lesson_charge(session, lesson)
        session.commit()

        assert _charges(session, lesson.id) == []
        assert balance(session, student_id) == 0


def test_charge_amount_follows_price(student_factory):
    """Правка цены пересчитывает существующую строку, а не создаёт вторую."""
    student_id = student_factory()

    with SessionLocal() as session:
        lesson = _lesson(session, student_id=student_id, price=1200)
        sync_lesson_charge(session, lesson)
        session.commit()
        original_id = _charges(session, lesson.id)[0].id

        lesson.price = 1500
        sync_lesson_charge(session, lesson)
        session.commit()

        charges = _charges(session, lesson.id)
        assert len(charges) == 1
        # upsert, а не «удалить и создать»: id строки сохраняется.
        assert charges[0].id == original_id
        assert charges[0].amount == 1500
        assert balance(session, student_id) == -1500


def test_charge_time_is_lesson_start(student_factory):
    """`occurred_at` списания — начало урока (design D15)."""
    student_id = student_factory()
    starts_at = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)

    with SessionLocal() as session:
        lesson = _lesson(session, student_id=student_id, starts_at=starts_at)
        sync_lesson_charge(session, lesson)
        session.commit()

        charge = _charges(session, lesson.id)[0]
        from app.tutor.services.clock import as_utc

        assert as_utc(charge.occurred_at) == starts_at


def test_sync_is_idempotent(student_factory):
    """Два вызова подряд не меняют число строк и баланс."""
    student_id = student_factory()

    with SessionLocal() as session:
        lesson = _lesson(session, student_id=student_id, price=1200)
        sync_lesson_charge(session, lesson)
        session.commit()
        sync_lesson_charge(session, lesson)
        session.commit()

        assert len(_charges(session, lesson.id)) == 1
        assert balance(session, student_id) == -1200


# --------------------------------------------------------------------------
# Групповой урок (задача 5.2)
# --------------------------------------------------------------------------


def test_group_lesson_charges_every_member_at_group_price(
    group_factory, student_factory, group_member_factory
):
    """Группа с ценой 1200 и два участника: по списанию на каждого."""
    group_id = group_factory(price_per_lesson=1200)
    first = student_factory(tutor_id=None)
    second = student_factory(tutor_id=None)
    group_member_factory(group_id=group_id, student_id=first)
    group_member_factory(group_id=group_id, student_id=second)

    with SessionLocal() as session:
        lesson = _lesson(session, group_id=group_id, price=None)

        assert sync_lesson_charge(session, lesson) == 2
        session.commit()

        charges = {row.student_id: row.amount for row in _charges(session, lesson.id)}
        assert charges == {first: 1200, second: 1200}
        assert balance(session, first) == -1200
        assert balance(session, second) == -1200


def test_group_member_price_override_wins(
    group_factory, student_factory, group_member_factory
):
    """Индивидуальная цена участника 1000 важнее общей 1200."""
    group_id = group_factory(price_per_lesson=1200)
    regular = student_factory()
    special = student_factory()
    group_member_factory(group_id=group_id, student_id=regular)
    group_member_factory(group_id=group_id, student_id=special, price_override=1000)

    with SessionLocal() as session:
        lesson = _lesson(session, group_id=group_id, price=None)
        sync_lesson_charge(session, lesson)
        session.commit()

        charges = {row.student_id: row.amount for row in _charges(session, lesson.id)}

    assert charges == {regular: 1200, special: 1000}


def test_group_without_price_creates_no_charges(
    group_factory, student_factory, group_member_factory
):
    """Группа без цены: списаний нет ни у кого."""
    group_id = group_factory(price_per_lesson=None)
    member = student_factory()
    group_member_factory(group_id=group_id, student_id=member)

    with SessionLocal() as session:
        lesson = _lesson(session, group_id=group_id, price=None)

        assert sync_lesson_charge(session, lesson) == 0
        session.commit()

        assert _charges(session, lesson.id) == []
        assert balance(session, member) == 0


def test_group_member_without_any_price_gets_no_charge(
    group_factory, student_factory, group_member_factory
):
    """Участник без цены (ни своей, ни общей) списания не получает."""
    group_id = group_factory(price_per_lesson=None)
    priced = student_factory()
    unpriced = student_factory()
    group_member_factory(group_id=group_id, student_id=priced, price_override=900)
    group_member_factory(group_id=group_id, student_id=unpriced)

    with SessionLocal() as session:
        lesson = _lesson(session, group_id=group_id, price=None)
        sync_lesson_charge(session, lesson)
        session.commit()

        charges = {row.student_id: row.amount for row in _charges(session, lesson.id)}

    assert charges == {priced: 900}


def test_member_leaving_group_removes_only_his_charge(
    group_factory, student_factory, group_member_factory
):
    """Вышедший из группы перестаёт списываться, остальные строки целы."""
    from app.group.models.group_member import GroupMember

    group_id = group_factory(price_per_lesson=1000)
    stays = student_factory()
    leaves = student_factory()
    group_member_factory(group_id=group_id, student_id=stays)
    member_id = group_member_factory(group_id=group_id, student_id=leaves)

    with SessionLocal() as session:
        lesson = _lesson(session, group_id=group_id, price=None)
        sync_lesson_charge(session, lesson)
        session.commit()
        assert len(_charges(session, lesson.id)) == 2

        session.delete(session.get(GroupMember, member_id))
        session.commit()

        sync_lesson_charge(session, lesson)
        session.commit()

        charges = _charges(session, lesson.id)
        assert [row.student_id for row in charges] == [stays]


def test_lesson_targets_are_empty_for_planned_group_lesson(group_factory):
    """У непроведённого группового урока целей нет вовсе."""
    group_id = group_factory(price_per_lesson=1200)

    with SessionLocal() as session:
        lesson = _lesson(session, group_id=group_id, price=None, status="planned")

        assert lesson_targets(session, lesson) == []
