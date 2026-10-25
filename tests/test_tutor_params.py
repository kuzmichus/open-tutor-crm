"""Тесты KV-хранилища параметров репетитора (`tutor_params`)."""

from sqlalchemy import text

from app.database import SessionLocal
from app.tutor.services.params import (
    all_params,
    delete_param,
    get_param,
    set_param,
)

TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"


def test_set_then_get_returns_value(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        set_param(db, tutor_id, "telegram_token", TOKEN)
        assert get_param(db, tutor_id, "telegram_token") == TOKEN


def test_set_twice_upserts_single_row(tutor_factory):
    """Повторная запись обновляет значение, а не добавляет строку."""
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        set_param(db, tutor_id, "telegram_token", "old-token")
        set_param(db, tutor_id, "telegram_token", TOKEN)

        assert get_param(db, tutor_id, "telegram_token") == TOKEN
        rows = db.execute(
            text("select count(*) from tutor_params where tutor_id = :t"),
            {"t": tutor_id},
        ).scalar()
        assert rows == 1


def test_get_missing_param_is_none(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        assert get_param(db, tutor_id, "telegram_token") is None


def test_delete_param_removes_row(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        set_param(db, tutor_id, "telegram_token", TOKEN)
        delete_param(db, tutor_id, "telegram_token")

        assert get_param(db, tutor_id, "telegram_token") is None


def test_delete_missing_param_is_noop(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        delete_param(db, tutor_id, "unknown")
        assert all_params(db, tutor_id) == {}


def test_all_params_returns_only_own(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        set_param(db, tutor_id, "telegram_token", TOKEN)
        set_param(db, tutor_id, "digest_seen", "yes")

        assert all_params(db, tutor_id) == {
            "telegram_token": TOKEN,
            "digest_seen": "yes",
        }


def test_params_are_isolated_by_tutor(tutor_factory):
    """Параметр репетитора A не виден репетитору B."""
    tutor_a = tutor_factory()
    tutor_b = tutor_factory()
    with SessionLocal() as db:
        set_param(db, tutor_a, "telegram_token", TOKEN)

        assert get_param(db, tutor_b, "telegram_token") is None
        assert all_params(db, tutor_b) == {}


def test_delete_cascades_with_tutor(tutor_factory):
    """Удаление репетитора уносит его параметры (FK CASCADE)."""
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        set_param(db, tutor_id, "telegram_token", TOKEN)
        db.execute(text("delete from tutors where id = :t"), {"t": tutor_id})
        db.commit()

        remaining = db.execute(
            text("select count(*) from tutor_params")
        ).scalar()
        assert remaining == 0
