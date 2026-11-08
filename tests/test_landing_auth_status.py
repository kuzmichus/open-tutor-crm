"""Тесты публичного статуса входа и клиентской подмены кнопок лендинга.

`GET /auth/status` отвечает булевыми признаками трёх независимых сессий
(ученик, родитель, репетитор) и не кэшируется. Скрипт `landing-auth.js`
меняет текст и `href` у `[data-auth]`, а без сессии или при сбое остаётся
обычной ссылкой на страницу входа.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.cabinet.models.contact_session import ContactSession
from app.cabinet.models.session import StudentSession
from app.cabinet.services.contact_sessions import (
    COOKIE_NAME as PARENT_COOKIE,
    create_session as create_contact_session,
)
from app.cabinet.services.sessions import (
    COOKIE_NAME as STUDENT_COOKIE,
    create_session as create_student_session,
)
from app.database import SessionLocal
from app.tutor.models.tutor_session import TutorSession
from app.tutor.services.sessions import (
    COOKIE_NAME as TUTOR_COOKIE,
    SessionService,
)

ROLES = ("student", "parent", "tutor")

COOKIE_NAMES = {
    "student": STUDENT_COOKIE,
    "parent": PARENT_COOKIE,
    "tutor": TUTOR_COOKIE,
}

SESSION_MODELS = {
    "student": StudentSession,
    "parent": ContactSession,
    "tutor": TutorSession,
}


@pytest.fixture()
def accounts(tutor_factory, student_factory, contact_factory):
    """Репетитор, его ученик и контакт родителя — по одному на каждую роль."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    contact_id = contact_factory(tutor_id=tutor_id)
    return {"student": student_id, "parent": contact_id, "tutor": tutor_id}


def _token(role, account_id):
    """Заводит живую сессию нужной роли и возвращает токен cookie."""
    with SessionLocal() as db:
        if role == "tutor":
            return SessionService().create(db, account_id)
        if role == "student":
            return create_student_session(db, account_id)
        return create_contact_session(db, account_id)


def _login(client, role, account_id):
    """Кладёт в клиент cookie живой сессии указанной роли."""
    token = _token(role, account_id)
    client.cookies.set(COOKIE_NAMES[role], token)
    return token


def _status(client):
    response = client.get("/auth/status", follow_redirects=False)
    assert response.status_code == 200
    return response


# --------------------------------------------------------------------------
# Аноним и заголовки
# --------------------------------------------------------------------------


def test_anonymous_status_is_false_for_all_roles(client):
    """Без cookie — три `false`, публичный ответ и запрет кэширования."""
    response = _status(client)

    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"student": False, "parent": False, "tutor": False}


def test_status_does_not_redirect_without_session(client):
    """Публичность: отсутствие сессии не превращается в редирект на вход."""
    response = client.get("/auth/status", follow_redirects=False)

    assert response.status_code == 200
    assert "location" not in response.headers


# --------------------------------------------------------------------------
# Одна живая сессия
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_single_session_marks_only_its_role(client, accounts, role):
    """Одна сессия включает только свой ключ, остальные остаются `false`."""
    _login(client, role, accounts[role])

    assert _status(client).json() == {name: name == role for name in ROLES}


# --------------------------------------------------------------------------
# Комбинации сессий
# --------------------------------------------------------------------------


def test_student_and_parent_sessions_are_independent(client, accounts):
    """Ученик и родитель в одном браузере дают два `true`, репетитор — `false`."""
    _login(client, "student", accounts["student"])
    _login(client, "parent", accounts["parent"])

    assert _status(client).json() == {
        "student": True,
        "parent": True,
        "tutor": False,
    }


def test_all_three_sessions_are_independent(client, accounts):
    """Все три сессии живут параллельно и дают три `true`."""
    for role in ROLES:
        _login(client, role, accounts[role])

    assert _status(client).json() == {
        "student": True,
        "parent": True,
        "tutor": True,
    }


# --------------------------------------------------------------------------
# Отсутствующие, лишние и протухшие cookie
# --------------------------------------------------------------------------


def test_forged_student_cookie_and_unknown_cookie_are_false(client):
    """Поддельный токен и незнакомое имя cookie не ломают ответ."""
    client.cookies.set(STUDENT_COOKIE, "forged-token")
    client.cookies.set("unexpected_cookie", "something")

    response = _status(client)

    assert response.json() == {"student": False, "parent": False, "tutor": False}


@pytest.mark.parametrize("role", ROLES)
def test_expired_session_is_false(client, accounts, role):
    """Протухшая сессия любой роли даёт `false`, остальные не затронуты."""
    token = _token(role, accounts[role])
    with SessionLocal() as db:
        row = (
            db.query(SESSION_MODELS[role])
            .filter_by(token=token)
            .one()
        )
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    client.cookies.set(COOKIE_NAMES[role], token)

    assert _status(client).json()[role] is False


# --------------------------------------------------------------------------
# Статика скрипта
# --------------------------------------------------------------------------


def test_landing_auth_script_is_served(client):
    """Скрипт отдаётся локальной статикой по пути из шаблона лендинга."""
    response = client.get("/static/landing-auth.js")

    assert response.status_code == 200
    script = response.text
    assert "DOMContentLoaded" in script
    assert 'fetch("/auth/status"' in script
    assert "[data-auth]" in script
    assert '"/student"' in script
    assert '"/parent"' in script
    assert '"/tutor/"' in script
    assert "В кабинет" in script
    assert "кабинет" in script
