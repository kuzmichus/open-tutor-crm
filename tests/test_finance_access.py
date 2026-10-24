"""Тесты доступа к операции счёта: чужая и несуществующая неразличимы.

Проверяется сервисный слой (`get_owned_operation`): именно он держит
правило «id операции и tutor_id ученика в одном SELECT». Чужая операция
обязана отвечать 404, а не 403 — существование чужой записи не
раскрывается (спека student-finance, «Изоляция счёта по репетитору»).
"""

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.access import get_owned_operation


def _fetch(operation_id: str) -> AccountOperation:
    with SessionLocal() as session:
        return session.get(AccountOperation, operation_id)


def test_owner_reads_own_operation(tutor_factory, student_factory, operation_factory):
    """Операция своего ученика находится по id."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    operation_id = operation_factory(student_id=student_id)

    with SessionLocal() as session:
        operation = get_owned_operation(session, operation_id, tutor_id)

    assert operation.id == operation_id
    assert operation.student_id == student_id


def test_foreign_operation_is_not_found(
    tutor_factory, student_factory, operation_factory
):
    """Операция ученика чужого репетитора — 404, а не 403."""
    owner_id = tutor_factory()
    stranger_id = tutor_factory()
    foreign_student = student_factory(tutor_id=stranger_id)
    operation_id = operation_factory(student_id=foreign_student)

    with SessionLocal() as session:
        with pytest.raises(HTTPException) as excinfo:
            get_owned_operation(session, operation_id, owner_id)

    assert excinfo.value.status_code == 404
    # Запись при этом существует: 404 — маска, а не отсутствие данных.
    assert _fetch(operation_id) is not None


def test_missing_operation_is_not_found(tutor_factory):
    """Несуществующая операция отвечает тем же 404, что и чужая."""
    tutor_id = tutor_factory()

    with SessionLocal() as session:
        with pytest.raises(HTTPException) as excinfo:
            get_owned_operation(
                session, "00000000-0000-4000-8000-000000000000", tutor_id
            )

    assert excinfo.value.status_code == 404


def test_foreign_and_missing_operations_are_indistinguishable(
    tutor_factory, student_factory, operation_factory
):
    """Чужая и несуществующая операции дают одинаковый ответ.

    Различимое поведение (например, 403 у чужой) раскрывало бы факт
    существования записи у другого репетитора.
    """
    owner_id = tutor_factory()
    foreign_student = student_factory(tutor_id=tutor_factory())
    foreign_id = operation_factory(student_id=foreign_student)
    missing_id = "00000000-0000-4000-8000-000000000001"

    answers = []
    for operation_id in (foreign_id, missing_id):
        with SessionLocal() as session:
            with pytest.raises(HTTPException) as excinfo:
                get_owned_operation(session, operation_id, owner_id)
        answers.append((excinfo.value.status_code, excinfo.value.detail))

    assert answers[0] == answers[1]
