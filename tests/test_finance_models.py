"""Тесты модели «Операция счёта»: закрытые списки, уникальность, каскады.

Проверяем именно БД, а не валидацию формы: инвариант должен держаться и
при записи в обход сервисов (ручная правка, восстановление из бэкапа).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.lesson.models.lesson import Lesson



def _occurred_at() -> datetime:
    return datetime(2026, 10, 22, 1, 31, tzinfo=UTC)


def _lesson(student_id: str, *, price: int = 1200, status: str = "completed") -> str:
    """Проведённый урок ученика; возвращает его id."""
    with SessionLocal() as session:
        lesson = Lesson(
            student_id=student_id,
            type="individual",
            starts_at=_occurred_at(),
            duration_min=60,
            price=price,
            status=status,
        )
        session.add(lesson)
        session.commit()
        return lesson.id


def test_lesson_student_unique_index_exists():
    """Частичный уникальный индекс `(lesson_id, student_id)` создан моделью."""
    indexes = {
        row[1]
        for row in SessionLocal()
        .execute(text("PRAGMA index_list('account_operations')"))
        .all()
    }
    assert "ux_account_operations_lesson_student" in indexes


def test_payment_is_saved_with_defaults(student_factory):
    """Платёж получает uuid4-id, сумму, статус, способ и комментарий."""
    student_id = student_factory()

    with SessionLocal() as session:
        operation = AccountOperation(
            student_id=student_id,
            kind="payment",
            amount=2000,
            occurred_at=_occurred_at(),
            status="paid",
            method="transfer",
            comment="За октябрь",
        )
        session.add(operation)
        session.commit()
        operation_id = operation.id

    with SessionLocal() as session:
        saved = session.get(AccountOperation, operation_id)
        assert len(saved.id) == 36
        assert saved.kind == "payment"
        assert saved.amount == 2000
        assert saved.status == "paid"
        assert saved.method == "transfer"
        assert saved.comment == "За октябрь"
        # SQLite теряет tzinfo — сравниваем наивное значение.
        assert saved.occurred_at == _occurred_at().replace(tzinfo=None)
        assert saved.created_at is not None
        assert saved.updated_at is not None


def test_refund_and_charge_have_no_status_or_method(student_factory):
    """Возврат и списание сохраняются с NULL в статусе и способе."""
    student_id = student_factory()
    lesson_id = _lesson(student_id)

    with SessionLocal() as session:
        session.add_all(
            [
                AccountOperation(
                    student_id=student_id,
                    kind="refund",
                    amount=500,
                    occurred_at=_occurred_at(),
                ),
                AccountOperation(
                    student_id=student_id,
                    kind="lesson",
                    amount=1200,
                    occurred_at=_occurred_at(),
                    lesson_id=lesson_id,
                ),
            ]
        )
        session.commit()

        kinds = {
            row.kind for row in session.query(AccountOperation).all()
        }
        assert kinds == {"refund", "lesson"}


def test_unknown_kind_is_rejected(student_factory, expect_integrity_error):
    """Вид операции вне закрытого списка отклоняется CHECK-ом."""
    student_id = student_factory()

    with expect_integrity_error() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="unknown",
                amount=100,
                occurred_at=_occurred_at(),
            )
        )


def test_non_positive_amount_is_rejected(student_factory, expect_integrity_error):
    """Сумма 0 и отрицательная сумма отклоняются: знак выводится из вида."""
    student_id = student_factory()

    for amount in (0, -100):
        with expect_integrity_error() as session:
            session.add(
                AccountOperation(
                    student_id=student_id,
                    kind="payment",
                    amount=amount,
                    occurred_at=_occurred_at(),
                    status="paid",
                    method="card",
                )
            )


def test_status_on_lesson_charge_is_rejected(student_factory, expect_integrity_error):
    """У списания за урок не может быть статуса платежа (design D4)."""
    student_id = student_factory()
    lesson_id = _lesson(student_id)

    with expect_integrity_error() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="lesson",
                amount=1200,
                occurred_at=_occurred_at(),
                lesson_id=lesson_id,
                status="paid",
            )
        )


def test_unknown_status_and_method_are_rejected(student_factory, expect_integrity_error):
    """Статус и способ вне закрытых списков не сохраняются."""
    student_id = student_factory()

    with expect_integrity_error() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="payment",
                amount=100,
                occurred_at=_occurred_at(),
                status="done",
                method="card",
            )
        )

    with expect_integrity_error() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="payment",
                amount=100,
                occurred_at=_occurred_at(),
                status="paid",
                method="crypto",
            )
        )


def test_two_charges_for_same_lesson_and_student_are_rejected(student_factory, expect_integrity_error):
    """Пара «урок + ученик» уникальна среди списаний."""
    student_id = student_factory()
    lesson_id = _lesson(student_id)

    with SessionLocal() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="lesson",
                amount=1200,
                occurred_at=_occurred_at(),
                lesson_id=lesson_id,
            )
        )
        session.commit()

    with expect_integrity_error() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="lesson",
                amount=1500,
                occurred_at=_occurred_at(),
                lesson_id=lesson_id,
            )
        )


def test_index_allows_duplicate_lesson_for_other_kind(student_factory):
    """Индекс частичный: платежи с тем же `lesson_id` он не ограничивает.

    Ограничение `(lesson_id, student_id)` относится только к списаниям —
    иначе будущий платёж «за конкретный урок» упирался бы в него.
    """
    student_id = student_factory()
    lesson_id = _lesson(student_id)

    with SessionLocal() as session:
        session.add_all(
            [
                AccountOperation(
                    student_id=student_id,
                    kind="lesson",
                    amount=1200,
                    occurred_at=_occurred_at(),
                    lesson_id=lesson_id,
                ),
                AccountOperation(
                    student_id=student_id,
                    kind="payment",
                    amount=1200,
                    occurred_at=_occurred_at(),
                    status="paid",
                    method="card",
                    lesson_id=lesson_id,
                ),
            ]
        )
        session.commit()

        assert session.query(AccountOperation).count() == 2


def test_deleting_lesson_cascades_its_charge(student_factory):
    """Удаление урока снимает списание через каскад `lesson_id`."""
    student_id = student_factory()
    lesson_id = _lesson(student_id)

    with SessionLocal() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="lesson",
                amount=1200,
                occurred_at=_occurred_at(),
                lesson_id=lesson_id,
            )
        )
        session.commit()

    with SessionLocal() as session:
        session.delete(session.get(Lesson, lesson_id))
        session.commit()

    with SessionLocal() as session:
        assert session.query(AccountOperation).all() == []


def test_deleting_student_cascades_operations(tutor_factory, student_factory):
    """Удаление ученика уносит все его операции."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="payment",
                amount=2000,
                occurred_at=_occurred_at(),
                status="paid",
                method="transfer",
            )
        )
        session.commit()

    from app.student.models.student import Student

    with SessionLocal() as session:
        session.delete(session.get(Student, student_id))
        session.commit()

    with SessionLocal() as session:
        assert session.query(AccountOperation).all() == []


def test_refund_keeps_history_when_payment_disappears(student_factory):
    """`payment_id` объявлен SET NULL: возврат переживает удаление платежа."""
    student_id = student_factory()

    with SessionLocal() as session:
        payment = AccountOperation(
            student_id=student_id,
            kind="payment",
            amount=2400,
            occurred_at=_occurred_at(),
            status="paid",
            method="card",
        )
        session.add(payment)
        session.flush()
        refund = AccountOperation(
            student_id=student_id,
            kind="refund",
            amount=1000,
            occurred_at=_occurred_at(),
            payment_id=payment.id,
        )
        session.add(refund)
        session.commit()
        payment_id, refund_id = payment.id, refund.id

    with SessionLocal() as session:
        session.delete(session.get(AccountOperation, payment_id))
        session.commit()

    with SessionLocal() as session:
        saved = session.get(AccountOperation, refund_id)
        assert saved is not None
        assert saved.payment_id is None


def test_operation_requires_existing_student(expect_integrity_error):
    """Операция без существующего ученика не сохраняется (FK)."""
    with expect_integrity_error() as session:
        session.add(
            AccountOperation(
                student_id="00000000-0000-4000-8000-000000000000",
                kind="payment",
                amount=100,
                occurred_at=_occurred_at(),
                status="paid",
                method="card",
            )
        )


@pytest.mark.parametrize("kind", ["payment", "refund", "lesson"])
def test_all_operation_kinds_are_saved(student_factory, kind):
    """Каждый вид из закрытого списка проходит CHECK-ограничение."""
    student_id = student_factory()
    lesson_id = _lesson(student_id) if kind == "lesson" else None

    with SessionLocal() as session:
        operation = AccountOperation(
            student_id=student_id,
            kind=kind,
            amount=100,
            occurred_at=_occurred_at(),
            status="paid" if kind == "payment" else None,
            method="card" if kind == "payment" else None,
            lesson_id=lesson_id,
        )
        session.add(operation)
        session.commit()
        assert session.get(AccountOperation, operation.id).kind == kind
