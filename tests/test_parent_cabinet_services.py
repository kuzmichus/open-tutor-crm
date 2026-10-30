"""Тесты сервисов кабинета родителя (change parent-cabinet).

Сессии контактов (`parent_session`), приглашение контакта (перевыпуск
гасит прежнюю ссылку), регистрация по приглашению (новый вход и поверх
существующего), дети контакта (все статусы, изоляция привязкой), ДЗ
ребёнка (заметка педагога не выбирается), финансы по детям (итог, без
роли плательщика).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.cabinet.models.contact_access import ContactAccess
from app.cabinet.models.contact_invite import ContactCabinetInvite
from app.cabinet.models.contact_session import ContactSession
from app.cabinet.services.child_finance import finance_overview
from app.cabinet.services.child_homework import child_homework
from app.cabinet.services.children import children, get_child
from app.cabinet.services.contact_invites import (
    badge_contexts,
    create_invite,
    find_valid_invite,
)
from app.cabinet.services.contact_registration import (
    ERROR_EMAIL_FORMAT,
    ERROR_EMAIL_TAKEN,
    ERROR_LINK_INVALID,
    ERROR_PASSWORD_SHORT,
    register_by_invite,
)
from app.cabinet.services.contact_sessions import (
    COOKIE_NAME,
    create_session,
    delete_session,
    get_contact_id,
)
from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.homework.models.homework import Homework
from app.student.models.contact import Contact
from app.student.models.student_access import MIN_PASSWORD_LENGTH
from app.student.models.student_contact import StudentContact


def _db():
    return SessionLocal()


def _link(student_id: str, contact_id: str) -> None:
    with _db() as db:
        db.add(StudentContact(student_id=student_id, contact_id=contact_id))
        db.commit()


# --------------------------------------------------------------------------
# 2.1 Сессии контактов
# --------------------------------------------------------------------------


def test_contact_session_create_and_revoke(client, contact_factory):
    contact_id = contact_factory()
    with _db() as db:
        token = create_session(db, contact_id)
        assert get_contact_id(db, token) == contact_id

        delete_session(db, token)
        assert get_contact_id(db, token) is None


def test_contact_session_expired_not_valid(client, contact_factory):
    contact_id = contact_factory()
    with _db() as db:
        token = create_session(db, contact_id)
        row = db.scalars(select(ContactSession)).first()
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
        assert get_contact_id(db, token) is None
        # TTL = 7 дней: только что созданная сессия живёт.
        fresh = create_session(db, contact_id)
        assert get_contact_id(db, fresh) == contact_id
        assert COOKIE_NAME == "parent_session"


# --------------------------------------------------------------------------
# 2.2 Приглашение контакта и бейджи
# --------------------------------------------------------------------------


def test_contact_invite_reissue_kills_old_link(client, tutor_factory, contact_factory):
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)
    with _db() as db:
        first = create_invite(db, tutor_id, contact_id)
        old_token = first.token
        second = create_invite(db, tutor_id, contact_id)

        assert find_valid_invite(db, old_token) is None
        assert find_valid_invite(db, second.token) == second


def test_contact_invite_expired_not_found(client, tutor_factory, contact_factory):
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)
    with _db() as db:
        invite = create_invite(db, tutor_id, contact_id)
        invite.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()
        assert find_valid_invite(db, invite.token) is None


def test_badge_contexts_all_states(client, tutor_factory, contact_factory):
    """Три контакта: без всего, с активной ссылкой, со входом и ссылкой."""
    tutor_id = tutor_factory()
    bare = contact_factory(tutor_id=tutor_id)
    invited = contact_factory(tutor_id=tutor_id)
    bound = contact_factory(tutor_id=tutor_id)

    with _db() as db:
        create_invite(db, tutor_id, invited)
        # Вход третьего контакта — строка ContactAccess напрямую.
        from app.tutor.services.password_hasher import PasswordHasher

        db.add(
            ContactAccess(
                contact_id=bound,
                email="parent-bound@example.com",
                password_hash=PasswordHasher().hash("пароль-пароль"),
            )
        )
        create_invite(db, tutor_id, bound)
        db.commit()

        contexts = badge_contexts(db, tutor_id, [bare, invited, bound])

    assert contexts[bare] == {
        "has_access": False,
        "email": "",
        "has_invite": False,
        "token": "",
    }
    assert contexts[invited]["has_invite"] is True
    assert contexts[invited]["has_access"] is False
    assert contexts[invited]["token"]
    assert contexts[bound]["has_access"] is True
    assert contexts[bound]["email"] == "parent-bound@example.com"
    # Вход и активная ссылка не исключают друг друга.
    assert contexts[bound]["has_invite"] is True


def test_badge_contexts_empty_list(client, tutor_factory):
    with _db() as db:
        assert badge_contexts(db, tutor_factory(), []) == {}


# --------------------------------------------------------------------------
# 2.3 Регистрация по приглашению
# --------------------------------------------------------------------------


def test_contact_registration_new_access(client, tutor_factory, contact_factory):
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)
    with _db() as db:
        invite = create_invite(db, tutor_id, contact_id)
        errors = register_by_invite(db, invite, "mama@example.com", "пароль-пароль")

        assert errors == []
        access = db.scalars(
            select(ContactAccess).where(ContactAccess.contact_id == contact_id)
        ).one()
        assert access.email == "mama@example.com"
        # Ссылка погашена: повторная регистрация по ней не проходит.
        assert find_valid_invite(db, invite.token) is None
        assert register_by_invite(db, invite, "mama@example.com", "пароль-пароль") == [
            ERROR_LINK_INVALID
        ]


def test_contact_registration_updates_existing_access(
    client, tutor_factory, contact_factory
):
    """Повторная регистрация по перевыпущенной ссылке обновляет вход."""
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)
    with _db() as db:
        from app.tutor.services.password_hasher import PasswordHasher

        db.add(
            ContactAccess(
                contact_id=contact_id,
                email="old@example.com",
                password_hash=PasswordHasher().hash("старый-пароль"),
            )
        )
        db.commit()

        create_invite(db, tutor_id, contact_id)
        invite = db.scalars(select(ContactCabinetInvite)).one()
        errors = register_by_invite(db, invite, "new@example.com", "новый-пароль")

        assert errors == []
        rows = db.scalars(
            select(ContactAccess).where(ContactAccess.contact_id == contact_id)
        ).all()
        assert len(rows) == 1
        assert rows[0].email == "new@example.com"
        assert PasswordHasher().verify("новый-пароль", rows[0].password_hash)


def test_contact_registration_taken_email_rejected(
    client, tutor_factory, contact_factory
):
    tutor_id = tutor_factory()
    first = contact_factory(tutor_id=tutor_id)
    second = contact_factory(tutor_id=tutor_id)
    with _db() as db:
        from app.tutor.services.password_hasher import PasswordHasher

        db.add(
            ContactAccess(
                contact_id=first,
                email="занят@example.com",
                password_hash=PasswordHasher().hash("пароль-пароль"),
            )
        )
        db.commit()

        create_invite(db, tutor_id, second)
        invite = db.scalars(select(ContactCabinetInvite)).one()
        assert register_by_invite(
            db, invite, "занят@example.com", "пароль-пароль"
        ) == [ERROR_EMAIL_TAKEN]
        # Ошибка валидации — ссылка не погашена, вход второго не создан.
        assert find_valid_invite(db, invite.token) is not None
        assert (
            db.scalars(
                select(ContactAccess).where(ContactAccess.contact_id == second)
            ).first()
            is None
        )


def test_contact_registration_validation_errors(client, tutor_factory, contact_factory):
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)
    with _db() as db:
        invite = create_invite(db, tutor_id, contact_id)
        assert register_by_invite(db, invite, "не-email", "пароль-пароль") == [
            ERROR_EMAIL_FORMAT
        ]
        short = "п" * (MIN_PASSWORD_LENGTH - 1)
        assert register_by_invite(db, invite, "mama@example.com", short) == [
            ERROR_PASSWORD_SHORT
        ]
        # Валидация не погасила ссылку.
        assert find_valid_invite(db, invite.token) is not None


# --------------------------------------------------------------------------
# 2.4 Дети контакта
# --------------------------------------------------------------------------


def test_children_lists_all_statuses(client, tutor_factory, student_factory, contact_factory):
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)
    active = student_factory(tutor_id=tutor_id, first_name="Аня")
    archived = student_factory(
        tutor_id=tutor_id, first_name="Боря", status="archived"
    )
    _link(active, contact_id)
    _link(archived, contact_id)

    with _db() as db:
        ids = {student.id for student in children(db, contact_id)}
    assert ids == {active, archived}


def test_get_child_unlinked_student_is_404(
    client, tutor_factory, student_factory, contact_factory
):
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)
    linked = student_factory(tutor_id=tutor_id)
    stranger = student_factory(tutor_id=tutor_id)
    _link(linked, contact_id)

    with _db() as db:
        assert get_child(db, linked, contact_id).id == linked
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            get_child(db, stranger, contact_id)
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc:
            get_child(db, "нет-такого-id", contact_id)
        assert exc.value.status_code == 404


# --------------------------------------------------------------------------
# 2.5 Домашние задания ребёнка
# --------------------------------------------------------------------------


def _make_homework(lesson_id: str, **extra) -> None:
    with _db() as db:
        db.add(
            Homework(
                lesson_id=lesson_id,
                assignment="Страница 12, упражнения 3–5",
                status="assigned",
                **extra,
            )
        )
        db.commit()


def test_child_homework_visible_without_teacher_note(
    client, tutor_factory, student_factory, contact_factory, lesson_factory
):
    """Задание видно, заметки педагога в контексте нет (D7)."""
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    _link(student_id, contact_id)
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2026, 11, 5, 15, 0, tzinfo=UTC),
    )
    _make_homework(
        lesson_id,
        teacher_note="Секретная заметка педагога",
        teacher_comment="Комментарий для ученика",
    )

    with _db() as db:
        cards = child_homework(db, student_id)

    assert len(cards) == 1
    card = cards[0]
    assert card.assignment == "Страница 12, упражнения 3–5"
    assert card.teacher_comment == "Комментарий для ученика"
    assert card.status == "assigned"
    # Заметка педагога не выбирается вовсе: поля нет ни с секретом, ни с None.
    assert "teacher_note" not in card.__dataclass_fields__


def test_child_homework_group_lesson_visible(
    client, tutor_factory, student_factory, group_factory, group_member_factory,
    lesson_factory, contact_factory,
):
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    _link(student_id, contact_id)
    group_id = group_factory(tutor_id=tutor_id)
    group_member_factory(group_id=group_id, student_id=student_id)
    lesson_id = lesson_factory(
        group_id=group_id,
        student_id=None,
        status="planned",
        starts_at=datetime(2026, 11, 6, 10, 0, tzinfo=UTC),
    )
    _make_homework(lesson_id)

    with _db() as db:
        cards = child_homework(db, student_id)
    assert len(cards) == 1
    assert cards[0].lesson_type == "group"


# --------------------------------------------------------------------------
# 2.6 Финансы по детям
# --------------------------------------------------------------------------


def test_finance_overview_two_children_and_total(
    client, tutor_factory, student_factory, contact_factory, operation_factory
):
    """Двое детей — два блока, итог равен сумме; плательщик не назначен."""
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id)  # плательщиком не назначен
    first = student_factory(tutor_id=tutor_id, first_name="Аня")
    second = student_factory(tutor_id=tutor_id, first_name="Боря")
    _link(first, contact_id)
    _link(second, contact_id)

    operation_factory(student_id=first, kind="payment", amount=3000, status="paid")
    operation_factory(student_id=second, kind="payment", amount=1500, status="paid")
    operation_factory(student_id=second, kind="lesson", amount=600)

    with _db() as db:
        blocks, total = finance_overview(db, contact_id)

    assert [block.student.id for block in blocks] == [first, second]
    assert blocks[0].balance == 3000
    assert blocks[0].payments_total == 3000
    assert blocks[1].balance == 1500 - 600
    assert blocks[1].payments_total == 1500
    # История содержит только операции, влияющие на баланс.
    assert len(blocks[1].history) == 2
    assert total == 3000 + (1500 - 600)


def test_finance_overview_empty_without_children(client, tutor_factory, contact_factory):
    contact_id = contact_factory(tutor_id=tutor_factory())
    with _db() as db:
        blocks, total = finance_overview(db, contact_id)
    assert blocks == []
    assert total == 0
