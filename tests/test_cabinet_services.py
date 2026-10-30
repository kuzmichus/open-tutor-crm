"""Тесты сервисов кабинета: сессии, приглашения, регистрация, «Мои уроки».

change student-cabinet-access: независимые сессии учеников (своя таблица
и cookie), одноразовое приглашение с гашением прежней ссылки, регистрация
по приглашению (новый вход и поверх ручного), ближайшие запланированные
уроки для вкладки «Мои уроки».
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.cabinet.models.invite import StudentCabinetInvite
from app.cabinet.models.session import StudentSession
from app.cabinet.services.invites import create_invite, find_valid_invite, invite_context
from app.cabinet.services.lessons import upcoming_lessons
from app.cabinet.services.registration import (
    ERROR_EMAIL_FORMAT,
    ERROR_EMAIL_TAKEN,
    ERROR_PASSWORD_SHORT,
    register_by_invite,
)
from app.cabinet.services.sessions import (
    COOKIE_NAME,
    create_session,
    delete_session,
    get_student_id,
)
from app.database import SessionLocal
from app.student.models.student_access import StudentAccess
from app.student.services.credentials import get_access
from app.tutor.services.password_hasher import PasswordHasher


def _db():
    return SessionLocal()


# --------------------------------------------------------------------------
# 2.1 Сессии ученика
# --------------------------------------------------------------------------


def test_student_session_create_and_revoke(client, student_factory):
    student_id = student_factory()
    with _db() as db:
        token = create_session(db, student_id)
        assert get_student_id(db, token) == student_id

        delete_session(db, token)
        assert get_student_id(db, token) is None


def test_student_session_expired_not_valid(client, student_factory):
    student_id = student_factory()
    with _db() as db:
        token = create_session(db, student_id)
        row = db.scalars(select(StudentSession)).first()
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
        assert get_student_id(db, token) is None
        # TTL = 7 дней: только что созданная сессия живёт.
        fresh = create_session(db, student_id)
        assert get_student_id(db, fresh) == student_id
        assert COOKIE_NAME == "student_session"


# --------------------------------------------------------------------------
# 2.2 Приглашение в кабинет
# --------------------------------------------------------------------------


def test_invite_create_and_reissue_kills_old_link(client, tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    with _db() as db:
        first = create_invite(db, tutor_id, student_id)
        old_token = first.token
        second = create_invite(db, tutor_id, student_id)

        # Одна строка на ученика, токен заменён, прежняя ссылка погашена.
        assert db.query(StudentCabinetInvite).count() == 1
        assert second.token != old_token
        assert find_valid_invite(db, old_token) is None
        assert find_valid_invite(db, second.token).id == second.id


def test_invite_expired_token_not_found(client, tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    with _db() as db:
        invite = create_invite(db, tutor_id, student_id)
        invite.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()
        assert find_valid_invite(db, invite.token) is None


def test_invite_context_states(client, tutor_factory, student_factory):
    """Три состояния блока: нет входа / ссылка активна / вход привязан."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)

    with _db() as db:
        context = invite_context(db, tutor_id, student_id)
        assert context == {
            "has_access": False,
            "email": "",
            "login": "",
            "has_invite": False,
            "token": "",
        }

        invite = create_invite(db, tutor_id, student_id)
        context = invite_context(db, tutor_id, student_id)
        assert context["has_access"] is False
        assert context["has_invite"] is True
        assert context["token"] == invite.token

        # Регистрация по ссылке: вход привязан, ссылка погашена.
        assert register_by_invite(
            db, invite, "masha@example.com", "пароль-пароль"
        ) == []
        context = invite_context(db, tutor_id, student_id)
        assert context["has_access"] is True
        assert context["email"] == "masha@example.com"
        assert context["has_invite"] is False


# --------------------------------------------------------------------------
# 2.3 Регистрация по приглашению
# --------------------------------------------------------------------------


@pytest.fixture()
def pending_invite(client, tutor_factory, student_factory):
    """Ученик с действующим приглашением; возвращает (tutor_id, student_id, invite)."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    with _db() as db:
        invite = create_invite(db, tutor_id, student_id)
    return tutor_id, student_id, invite.token


def _fresh_invite(token: str) -> StudentCabinetInvite | None:
    with _db() as db:
        return find_valid_invite(db, token)


def test_register_creates_access(client, pending_invite):
    tutor_id, student_id, token = pending_invite
    invite = _fresh_invite(token)
    with _db() as db:
        assert register_by_invite(db, invite, "masha@example.com", "пароль-пароль") == []

    with _db() as db:
        access = get_access(db, student_id)
        assert access.email == "masha@example.com"
        assert PasswordHasher().verify("пароль-пароль", access.password_hash)
        # Токен погашен той же транзакцией.
        assert _fresh_invite(token) is None


def test_register_updates_existing_manual_access(client, pending_invite):
    """Регистрация поверх ручного входа: email и пароль обновлены, карточка та же."""
    tutor_id, student_id, token = pending_invite
    with _db() as db:
        db.add(
            StudentAccess(
                student_id=student_id,
                login="masha",
                password_hash=PasswordHasher().hash("старый-пароль"),
            )
        )
        db.commit()

    invite = _fresh_invite(token)
    with _db() as db:
        assert register_by_invite(db, invite, "masha@example.com", "новый-пароль") == []

    with _db() as db:
        assert db.query(StudentAccess).filter_by(student_id=student_id).count() == 1
        access = get_access(db, student_id)
        assert access.login == "masha"
        assert access.email == "masha@example.com"
        assert PasswordHasher().verify("новый-пароль", access.password_hash)


def test_register_rejects_taken_email(client, pending_invite, student_factory):
    tutor_id, student_id, token = pending_invite
    other_student = student_factory(tutor_id=tutor_id)
    with _db() as db:
        db.add(
            StudentAccess(
                student_id=other_student,
                login="other",
                email="busy@example.com",
                password_hash=PasswordHasher().hash("пароль-пароль"),
            )
        )
        db.commit()

    invite = _fresh_invite(token)
    with _db() as db:
        assert register_by_invite(
            db, invite, "busy@example.com", "пароль-пароль"
        ) == [ERROR_EMAIL_TAKEN]
        assert get_access(db, student_id) is None
        # Ошибка валидации не погашает ссылку.
        assert _fresh_invite(token) is not None


def test_register_rejects_bad_values(client, pending_invite):
    tutor_id, student_id, token = pending_invite
    invite = _fresh_invite(token)
    with _db() as db:
        assert register_by_invite(db, invite, "не-email", "пароль-пароль") == [
            ERROR_EMAIL_FORMAT
        ]
        assert register_by_invite(db, invite, "masha@example.com", "коротко") == [
            ERROR_PASSWORD_SHORT
        ]
        assert get_access(db, student_id) is None


def test_consumed_link_does_not_work_twice(client, pending_invite):
    """Одноразовость: погашенная ссылка не работает повторно."""
    tutor_id, student_id, token = pending_invite
    invite = _fresh_invite(token)
    with _db() as db:
        assert register_by_invite(db, invite, "masha@example.com", "пароль-пароль") == []
    assert _fresh_invite(token) is None


# --------------------------------------------------------------------------
# 2.4 «Мои уроки»
# --------------------------------------------------------------------------


def _future(hours: int) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


def test_upcoming_lessons_nearest_first(client, lesson_factory, student_factory):
    student_id = student_factory()
    far = lesson_factory(student_id=student_id, status="planned", starts_at=_future(48))
    nearest = lesson_factory(
        student_id=student_id, status="planned", starts_at=_future(2)
    )

    with _db() as db:
        rows = upcoming_lessons(db, student_id)
    assert [lesson.id for lesson in rows] == [nearest, far]


def test_upcoming_lessons_hide_past_and_completed(client, lesson_factory, student_factory):
    student_id = student_factory()
    lesson_factory(student_id=student_id, status="planned", starts_at=_future(-2))
    lesson_factory(student_id=student_id, status="completed", starts_at=_future(2))

    with _db() as db:
        assert upcoming_lessons(db, student_id) == []


def test_upcoming_lessons_include_group(client, lesson_factory, student_factory,
                                        group_factory, group_member_factory):
    student_id = student_factory()
    group_id = group_factory()
    group_member_factory(group_id=group_id, student_id=student_id)
    group_lesson = lesson_factory(
        group_id=group_id, status="planned", starts_at=_future(24)
    )

    with _db() as db:
        rows = upcoming_lessons(db, student_id)
    assert [lesson.id for lesson in rows] == [group_lesson]


def test_upcoming_lessons_limited(client, lesson_factory, student_factory):
    from app.cabinet.services.lessons import UPCOMING_LIMIT

    student_id = student_factory()
    for hours in range(UPCOMING_LIMIT + 3):
        lesson_factory(
            student_id=student_id,
            status="planned",
            starts_at=_future(hours + 1),
        )

    with _db() as db:
        rows = upcoming_lessons(db, student_id)
    assert len(rows) == UPCOMING_LIMIT
