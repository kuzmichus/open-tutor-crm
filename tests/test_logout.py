"""Тесты выхода из системы (`/tutor/logout`)."""

from app.database import SessionLocal
from app.tutor.models.tutor_session import TutorSession
from app.tutor.services.sessions import COOKIE_NAME

PASSWORD = "Секретный-Пароль-1"


def _login(client, email="logout-user@example.com"):
    client.post(
        "/tutor/register",
        data={
            "name": "Выходящий",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )
    return client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )


def test_logout_redirects_to_login(client):
    _login(client)
    response = client.post("/tutor/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_logout_deletes_session_row(client):
    _login(client)
    with SessionLocal() as db:
        assert db.query(TutorSession).count() == 1

    client.post("/tutor/logout")

    with SessionLocal() as db:
        assert db.query(TutorSession).count() == 0


def test_cabinet_closed_after_logout(client):
    _login(client)
    # Cookie должна ещё быть у клиента, пока сервер её не сбросил.
    client.post("/tutor/logout")
    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_logout_clears_cookie(client):
    _login(client)
    response = client.post("/tutor/logout", follow_redirects=False)
    cookie_header = ";".join(response.headers.get_list("set-cookie")).lower()
    assert f"{COOKIE_NAME}=" in cookie_header


def test_old_cookie_rejected_after_logout(client):
    """Прежняя cookie не действует после выхода (сервер удалил сессию)."""
    _login(client)
    old_token = client.cookies.get(COOKIE_NAME)
    assert old_token

    client.post("/tutor/logout")

    # Клиент сбрасывает cookie, но подставим прежний токен вручную.
    client.cookies.set(COOKIE_NAME, old_token)
    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_logout_without_session_is_noop(client):
    response = client.post("/tutor/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_full_login_logout_login_cycle(client):
    """Вход → выход → повторный вход работает."""
    _login(client)
    client.post("/tutor/logout")

    response = client.post(
        "/tutor/login",
        data={"email": "logout-user@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/"

    cabinet = client.get("/tutor/")
    assert cabinet.status_code == 200
    assert "Выходящий" in cabinet.text
