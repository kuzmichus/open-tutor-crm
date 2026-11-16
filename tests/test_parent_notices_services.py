"""Тесты сервисов плашек кабинета родителя (change parent-cabinet-unified-pages).

Плашка срока домашних заданий (`homework_deadline.py`): статусы «Задано»
и «Не выполнено» считаются, «Сдано»/«Проверено» — нет; день — в зоне
репетитора; состав для ключа закрытия. Алерты нехватки и задолженности
(`notices.py`). Даты — `utcnow() ± timedelta` или «сегодня» зоны UTC
(фиксированные даты протухают).
"""

from datetime import time, timedelta

from app.cabinet.services.children import children as contact_children
from app.cabinet.services.homework_deadline import homework_deadline_notice
from app.cabinet.services.notices import debt_notice, today_shortfall_notice
from app.database import SessionLocal
from app.homework.models.homework import Homework
from app.student.models.student_contact import StudentContact
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow


def _link(student_id: str, contact_id: str) -> None:
    with SessionLocal() as db:
        db.add(StudentContact(student_id=student_id, contact_id=contact_id))
        db.commit()


def _at_today(hour: int):
    """Полдень «сегодня» зоны UTC: сегодня в любой момент суток."""
    from datetime import UTC, datetime

    return datetime.combine(utcnow().date(), time(hour, 0), tzinfo=UTC)


def _at_yesterday(hour: int = 12):
    from datetime import UTC, datetime, timedelta

    return datetime.combine(
        utcnow().date() - timedelta(days=1), time(hour, 0), tzinfo=UTC
    )


def _make_homework(lesson_id: str, status: str, due_at) -> str:
    with SessionLocal() as db:
        homework = Homework(
            lesson_id=lesson_id,
            assignment="Упражнение №3",
            status=status,
            due_at=due_at,
        )
        db.add(homework)
        db.commit()
        return homework.id


def test_deadline_today_counts(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """«Задано» со сроком сегодня попадает в плашку."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    lesson_id = lesson_factory(student_id=anya, status="planned", price=0)
    homework_id = _make_homework(lesson_id, "assigned", _at_today(12))

    with SessionLocal() as db:
        notice = homework_deadline_notice(
            db, contact_children(db, contact_id), db.get(Tutor, tutor_id)
        )
    assert notice is not None
    assert notice.homework_ids == (homework_id,)
    assert notice.count == 1


def test_deadline_expired_counts(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """«Не выполнено» с истёкшим сроком попадает в плашку."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    lesson_id = lesson_factory(student_id=anya, status="planned", price=0)
    homework_id = _make_homework(lesson_id, "not_done", _at_yesterday())

    with SessionLocal() as db:
        notice = homework_deadline_notice(
            db, contact_children(db, contact_id), db.get(Tutor, tutor_id)
        )
    assert notice is not None
    assert notice.homework_ids == (homework_id,)


def test_deadline_submitted_and_checked_ignored(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """«Сдано» и «Проверено» с горящим сроком не считаются."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    first = lesson_factory(student_id=anya, status="planned", price=0)
    second = lesson_factory(student_id=anya, status="planned", price=0)
    _make_homework(first, "submitted", _at_today(12))
    _make_homework(second, "checked", _at_yesterday())

    with SessionLocal() as db:
        notice = homework_deadline_notice(
            db, contact_children(db, contact_id), db.get(Tutor, tutor_id)
        )
    assert notice is None


def test_deadline_future_due_ignored(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Срок в будущем — плашки нет."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    lesson_id = lesson_factory(student_id=anya, status="planned", price=0)
    _make_homework(lesson_id, "assigned", utcnow() + timedelta(days=3))

    with SessionLocal() as db:
        notice = homework_deadline_notice(
            db, contact_children(db, contact_id), db.get(Tutor, tutor_id)
        )
    assert notice is None


def test_deadline_no_due_at_ignored(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Задание без срока в подсчёт не попадает: сравнивать не с чем."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    lesson_id = lesson_factory(student_id=anya, status="planned", price=0)
    _make_homework(lesson_id, "assigned", None)

    with SessionLocal() as db:
        notice = homework_deadline_notice(
            db, contact_children(db, contact_id), db.get(Tutor, tutor_id)
        )
    assert notice is None


def test_deadline_group_lesson_counts(
    tutor_factory, contact_factory, student_factory, group_factory,
    group_member_factory, lesson_factory,
):
    """Групповое задание ребёнка учится наравне с индивидуальным."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    group_id = group_factory(tutor_id=tutor_id)
    group_member_factory(group_id=group_id, student_id=anya)
    lesson_id = lesson_factory(
        group_id=group_id, student_id=None, status="planned", price=0
    )
    homework_id = _make_homework(lesson_id, "assigned", _at_yesterday())

    with SessionLocal() as db:
        notice = homework_deadline_notice(
            db, contact_children(db, contact_id), db.get(Tutor, tutor_id)
        )
    assert notice is not None
    assert notice.homework_ids == (homework_id,)


def test_deadline_close_key_changes_with_day(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Ключ закрытия включает день: закрытое сегодня не прячет завтрашнее."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    lesson_id = lesson_factory(student_id=anya, status="planned", price=0)
    _make_homework(lesson_id, "assigned", _at_today(12))

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        today = homework_deadline_notice(
            db, contact_children(db, contact_id), tutor, day=utcnow().date()
        )
        tomorrow = homework_deadline_notice(
            db,
            contact_children(db, contact_id),
            tutor,
            day=utcnow().date() + timedelta(days=1),
        )
        assert today is not None and tomorrow is not None
        assert today.close_key().startswith("hw-deadline:")
        assert today.close_key() != tomorrow.close_key()


# --------------------------------------------------------------------------
# Алерты родителя: нехватка на сегодня и задолженность (design D6)
# --------------------------------------------------------------------------


def test_shortfall_when_price_exceeds_balance(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Урок сегодня дороже баланса — плашка нехватки с суммой."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    # Урок сегодня (зона UTC), цена 1200, на счёте ничего.
    lesson_factory(
        student_id=anya, status="planned", price=1200, starts_at=_at_today(12)
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        notice = today_shortfall_notice(
            db, tutor, contact_children(db, contact_id)
        )
    assert notice is not None
    assert notice["students"] == 1
    assert notice["missing"] == 1200
    assert notice["day"] == utcnow().date()


def test_no_shortfall_when_balance_covers(
    tutor_factory, contact_factory, student_factory, lesson_factory, operation_factory
):
    """Баланс покрывает занятия дня — плашки нет."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    lesson_factory(
        student_id=anya, status="planned", price=1200, starts_at=_at_today(12)
    )
    operation_factory(student_id=anya, kind="payment", amount=1500, status="paid")

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        notice = today_shortfall_notice(
            db, tutor, contact_children(db, contact_id)
        )
    assert notice is None


def test_shortfall_ignores_lessons_of_other_children(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Уроки учеников педагога, не привязанных к контакту, не считаются."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    stranger = student_factory(tutor_id=tutor_id, first_name="Чужой")
    lesson_factory(
        student_id=stranger,
        status="planned",
        price=1200,
        starts_at=_at_today(12),
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        notice = today_shortfall_notice(
            db, tutor, contact_children(db, contact_id)
        )
    assert notice is None


def test_debt_notice_negative_balance_only(
    tutor_factory, contact_factory, student_factory, operation_factory
):
    """Отрицательный баланс попадает в плашку, положительный — нет."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    debtor = student_factory(tutor_id=tutor_id, first_name="Аня")
    solvent = student_factory(tutor_id=tutor_id, first_name="Боря")
    _link(debtor, contact_id)
    _link(solvent, contact_id)
    # Списание за урок без пополнения — баланс −600; пополнение — плюс.
    operation_factory(student_id=debtor, kind="lesson", amount=600)
    operation_factory(
        student_id=solvent, kind="payment", amount=1500, status="paid"
    )

    with SessionLocal() as db:
        notice = debt_notice(db, contact_children(db, contact_id))
    assert notice is not None
    assert notice["names"] == ["Аня"]
    assert notice["total"] == 600
    assert solvent not in notice["student_ids"]


def test_debt_notice_none_when_all_positive(
    tutor_factory, contact_factory, student_factory, operation_factory
):
    """Все балансы неотрицательные — плашки нет."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    operation_factory(
        student_id=anya, kind="payment", amount=1000, status="paid"
    )

    with SessionLocal() as db:
        notice = debt_notice(db, contact_children(db, contact_id))
    assert notice is None
