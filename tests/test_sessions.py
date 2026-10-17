"""Тесты `SessionService`."""

from datetime import UTC, datetime, timedelta

from app.database import SessionLocal
from app.tutor.models.tutor_session import TutorSession
from app.tutor.services.sessions import SessionService


def test_create_returns_valid_token(tutor_factory):
    tutor_id = tutor_factory()
    service = SessionService()
    with SessionLocal() as db:
        token = service.create(db, tutor_id)
        assert token
        assert service.get_tutor_id(db, token) == tutor_id


def test_unknown_or_forged_token_rejected(tutor_factory):
    tutor_factory()
    service = SessionService()
    with SessionLocal() as db:
        assert service.get_tutor_id(db, "поддельный-токен") is None
        assert service.get_tutor_id(db, None) is None
        assert service.get_tutor_id(db, "") is None


def test_expired_session_rejected(tutor_factory):
    tutor_id = tutor_factory()
    service = SessionService()
    with SessionLocal() as db:
        expired = TutorSession(
            tutor_id=tutor_id,
            token="истёкший-токен",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(expired)
        db.commit()
        assert service.get_tutor_id(db, "истёкший-токен") is None


def test_deleted_session_rejected(tutor_factory):
    tutor_id = tutor_factory()
    service = SessionService()
    with SessionLocal() as db:
        token = service.create(db, tutor_id)
        assert service.get_tutor_id(db, token) == tutor_id

        service.delete(db, token)
        assert service.get_tutor_id(db, token) is None


def test_delete_unknown_token_is_noop():
    service = SessionService()
    with SessionLocal() as db:
        service.delete(db, "нет-такого")
        service.delete(db, None)
