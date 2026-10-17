"""Тесты `PasswordResetService`."""

from datetime import UTC, datetime, timedelta

from app.database import SessionLocal
from app.tutor.models.password_reset_token import PasswordResetToken
from app.tutor.services.clock import as_utc
from app.tutor.services.password_reset import PasswordResetService


def test_fresh_key_is_valid(tutor_factory):
    tutor_id = tutor_factory()
    service = PasswordResetService()
    with SessionLocal() as db:
        token = service.create(db, tutor_id)
        assert token
        assert service.get_tutor_id(db, token) == tutor_id


def test_unknown_key_rejected(tutor_factory):
    tutor_factory()
    service = PasswordResetService()
    with SessionLocal() as db:
        assert service.get_tutor_id(db, "нет-такого-ключа") is None
        assert service.get_tutor_id(db, None) is None
        assert service.get_tutor_id(db, "") is None


def test_expired_key_rejected(tutor_factory):
    tutor_id = tutor_factory()
    service = PasswordResetService()
    with SessionLocal() as db:
        expired = PasswordResetToken(
            tutor_id=tutor_id,
            token="истёкший-ключ",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(expired)
        db.commit()
        assert service.get_tutor_id(db, "истёкший-ключ") is None


def test_consumed_key_rejected(tutor_factory):
    tutor_id = tutor_factory()
    service = PasswordResetService()
    with SessionLocal() as db:
        token = service.create(db, tutor_id)
        assert service.get_tutor_id(db, token) == tutor_id

        service.consume(db, token)
        assert service.get_tutor_id(db, token) is None


def test_two_keys_differ(tutor_factory):
    tutor_id = tutor_factory()
    service = PasswordResetService()
    with SessionLocal() as db:
        assert service.create(db, tutor_id) != service.create(db, tutor_id)


def test_ttl_is_at_most_24_hours(tutor_factory):
    tutor_id = tutor_factory()
    service = PasswordResetService()
    with SessionLocal() as db:
        token = service.create(db, tutor_id)
        row = (
            db.query(PasswordResetToken).filter_by(token=token).one()
        )
        remaining = as_utc(row.expires_at) - datetime.now(UTC)
        assert remaining <= timedelta(hours=24)
        assert remaining > timedelta(hours=23)
