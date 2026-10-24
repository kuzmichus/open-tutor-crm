"""Пересчёт баланса и детектор расхождения (задачи 6.1–6.2).

Проверяется правило «ремонт, а не переписывание истории» (design D7):
пересчёт добавляет недостающие списания, не трогает существующие суммы и
удаляет строки уроков, которые больше не проведены. Детектор расхождения
(design D8) обязан смотреть теми же глазами, что и пересчёт, — иначе
баннер останется висеть после ремонта.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import balance
from app.finance.services.recalculate import (
    has_missing_charges,
    recalculate,
)
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson


def _lesson(
    session,
    *,
    student_id=None,
    group_id=None,
    price=1200,
    status="completed",
    starts_at=None,
) -> Lesson:
    """Урок напрямую в БД — без списания: его создаёт только пересчёт."""
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


def _charges(student_id: str) -> list[AccountOperation]:
    """Списания ученика, от старых к новым."""
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(AccountOperation)
                .where(
                    AccountOperation.student_id == student_id,
                    AccountOperation.kind == "lesson",
                )
                .order_by(AccountOperation.created_at)
            ).all()
        )


def test_recalculate_adds_missing_charge(student_factory):
    """Проведённый урок без списания получает его после пересчёта."""
    student_id = student_factory()
    with SessionLocal() as session:
        lesson = _lesson(session, student_id=student_id, price=1200)

    with SessionLocal() as session:
        added = recalculate(session, _tutor_of(student_id), student_id)

    assert added == 1
    charges = _charges(student_id)
    assert len(charges) == 1
    assert charges[0].amount == 1200
    assert charges[0].lesson_id == lesson.id
    assert balance_for(student_id) == -1200


def test_recalculate_is_idempotent(student_factory):
    """Два пересчёта подряд не меняют ни число строк, ни баланс."""
    student_id = student_factory()
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200)

    tutor_id = _tutor_of(student_id)
    with SessionLocal() as session:
        assert recalculate(session, tutor_id, student_id) == 1
    with SessionLocal() as session:
        assert recalculate(session, tutor_id, student_id) == 0

    assert len(_charges(student_id)) == 1
    assert balance_for(student_id) == -1200


def test_recalculate_does_not_rewrite_existing_amount(student_factory, group_factory, group_member_factory):
    """Смена цены группы не переписывает уже созданное списание."""
    group_id = group_factory(price_per_lesson=1200)
    student_id = student_factory(tutor_id=_group_tutor(group_id))
    group_member_factory(group_id=group_id, student_id=student_id)
    with SessionLocal() as session:
        _lesson(session, group_id=group_id, price=None)

    tutor_id = _tutor_of(student_id)
    with SessionLocal() as session:
        assert recalculate(session, tutor_id, student_id) == 1

    with SessionLocal() as session:
        group = session.get(Group, group_id)
        group.price_per_lesson = 1500
        session.commit()

    with SessionLocal() as session:
        assert recalculate(session, tutor_id, student_id) == 0

    charges = _charges(student_id)
    assert [charge.amount for charge in charges] == [1200]


def test_recalculate_removes_charge_of_planned_lesson(student_factory):
    """Урок вернулся в «Запланирован» — пересчёт снимает его списание."""
    student_id = student_factory()
    with SessionLocal() as session:
        lesson = _lesson(session, student_id=student_id, price=1200)

    tutor_id = _tutor_of(student_id)
    with SessionLocal() as session:
        recalculate(session, tutor_id, student_id)

    with SessionLocal() as session:
        stored = session.get(Lesson, lesson.id)
        stored.status = "planned"
        session.commit()

    with SessionLocal() as session:
        recalculate(session, tutor_id, student_id)

    assert _charges(student_id) == []
    assert balance_for(student_id) == 0


def test_recalculate_ignores_lesson_without_price(student_factory):
    """Урок без цены не даёт списания — даже проведённый."""
    student_id = student_factory()
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=None)

    with SessionLocal() as session:
        assert recalculate(session, _tutor_of(student_id), student_id) == 0

    assert _charges(student_id) == []


def test_recalculate_foreign_student_changes_nothing(student_factory):
    """Ученик другого репетитора не ремонтируется сервисом."""
    student_id = student_factory()
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200)

    with SessionLocal() as session:
        assert recalculate(session, "чужой-репетитор", student_id) == 0

    assert _charges(student_id) == []


def test_detector_reports_missing_charge(student_factory):
    """Проведённый урок с ценой без списания — расхождение найдено."""
    student_id = student_factory()
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200)

    with SessionLocal() as session:
        assert has_missing_charges(session, _tutor_of(student_id), student_id) is True


def test_detector_silent_after_recalculate(student_factory):
    """После ремонта расхождения нет — баннер исчезает."""
    student_id = student_factory()
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200)

    tutor_id = _tutor_of(student_id)
    with SessionLocal() as session:
        recalculate(session, tutor_id, student_id)
    with SessionLocal() as session:
        assert has_missing_charges(session, tutor_id, student_id) is False


def test_detector_silent_for_planned_lesson(student_factory):
    """Запланированный урок расхождением не считается."""
    student_id = student_factory()
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=1200, status="planned")

    with SessionLocal() as session:
        assert has_missing_charges(session, _tutor_of(student_id), student_id) is False


def test_detector_silent_for_lesson_without_price(student_factory):
    """Урок без цены не создаёт списания, значит и расхождения нет."""
    student_id = student_factory()
    with SessionLocal() as session:
        _lesson(session, student_id=student_id, price=None)

    with SessionLocal() as session:
        assert has_missing_charges(session, _tutor_of(student_id), student_id) is False


def test_detector_reports_group_lesson_missing_charge(
    student_factory, group_factory, group_member_factory
):
    """Групповой урок без списаний — расхождение у каждого участника."""
    group_id = group_factory(price_per_lesson=1200)
    student_id = student_factory(tutor_id=_group_tutor(group_id))
    group_member_factory(group_id=group_id, student_id=student_id)
    with SessionLocal() as session:
        _lesson(session, group_id=group_id, price=None)

    with SessionLocal() as session:
        assert has_missing_charges(session, _tutor_of(student_id), student_id) is True


def test_detector_counts_member_override(
    student_factory, group_factory, group_member_factory
):
    """Индивидуальная цена участника делает цену группы необязательной."""
    group_id = group_factory(price_per_lesson=None)
    student_id = student_factory(tutor_id=_group_tutor(group_id))
    group_member_factory(group_id=group_id, student_id=student_id, price_override=1000)
    with SessionLocal() as session:
        _lesson(session, group_id=group_id, price=None)

    with SessionLocal() as session:
        assert has_missing_charges(session, _tutor_of(student_id), student_id) is True


def _tutor_of(student_id: str) -> str:
    """Репетитор ученика — для вызова сервисов."""
    from app.student.models.student import Student

    with SessionLocal() as session:
        return session.get(Student, student_id).tutor_id


def _group_tutor(group_id: str) -> str:
    """Репетитор группы — чтобы участник принадлежал тому же репетитору."""
    from app.group.models.group import Group

    with SessionLocal() as session:
        return session.get(Group, group_id).tutor_id


def balance_for(student_id: str) -> int:
    """Баланс ученика в отдельной сессии."""
    with SessionLocal() as session:
        return balance(session, student_id)
