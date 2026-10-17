"""Тесты личного кабинета (`/tutor/`)."""

from app.database import SessionLocal
from app.tutor.models.tutor_session import TutorSession
from app.tutor.services.sessions import COOKIE_NAME, SessionService

PASSWORD = "Секретный-Пароль-1"


def _login(client, email="home-user@example.com", password=PASSWORD, name="Кабинетный"):
    client.post(
        "/tutor/register",
        data={
            "name": name,
            "email": email,
            "password": password,
            "password_confirm": password,
        },
    )
    return client.post(
        "/tutor/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def test_redirect_to_login_without_session(client):
    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_cabinet_shows_own_data(client):
    _login(client)
    response = client.get("/tutor/")
    assert response.status_code == 200
    assert "Кабинетный" in response.text
    assert "home-user@example.com" in response.text


def test_cabinet_shows_profile_fields(client, tutor_factory):
    """Кабинет отображает необязательные поля карточки, если они заданы."""
    tutor_factory(
        name="Полный Профиль",
        email="full@example.com",
        password=PASSWORD,
        phone="+7 900 000-00-00",
        about="Рассказ о себе",
        subject="Физика",
        experience="10 лет",
        hourly_rate=2000,
        timezone="Europe/Moscow",
    )
    client.post(
        "/tutor/login",
        data={"email": "full@example.com", "password": PASSWORD},
    )
    response = client.get("/tutor/")
    for fragment in (
        "+7 900 000-00-00",
        "Рассказ о себе",
        "Физика",
        "10 лет",
        "2000",
        "Europe/Moscow",
    ):
        assert fragment in response.text


def test_cabinet_hides_other_tutors_data(client, tutor_factory):
    """Вошедший видит только свои данные, а не чужие."""
    tutor_factory(
        name="Чужой Репетитор",
        email="chuzhoy@example.com",
        password=PASSWORD,
    )
    _login(client, email="mine@example.com", name="Мой")

    response = client.get("/tutor/")
    assert "Мой" in response.text
    assert "Чужой Репетитор" not in response.text
    assert "chuzhoy@example.com" not in response.text


def test_password_never_rendered(client):
    _login(client)
    response = client.get("/tutor/")
    with SessionLocal() as db:
        from app.tutor.models.tutor import Tutor

        tutor = db.query(Tutor).filter_by(email="home-user@example.com").one()
    assert PASSWORD not in response.text
    assert tutor.password_hash not in response.text


def test_forged_token_redirects(client):
    """Подделанный/неизвестный токен в cookie приводит к редиректу на вход."""
    client.cookies.set(COOKIE_NAME, "forged-token-not-in-db")
    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_expired_session_redirects(client, tutor_factory):
    """Истёкшая сессия не открывает кабинет."""
    tutor_id = tutor_factory(email="exp@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "exp@example.com", "password": PASSWORD},
    )
    # Прорастить срок жизни в прошлое.
    with SessionLocal() as db:
        service = SessionService()
        from datetime import timedelta

        from app.tutor.services.clock import utcnow

        for row in db.query(TutorSession).filter_by(tutor_id=tutor_id).all():
            row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_session_of_deleted_tutor_redirects(client, tutor_factory):
    """Сессия удалённого репетитора не открывает кабинет."""
    from app.database import SessionLocal
    from app.tutor.models.tutor import Tutor

    tutor_id = tutor_factory(email="gone@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "gone@example.com", "password": PASSWORD},
    )
    with SessionLocal() as db:
        db.delete(db.get(Tutor, tutor_id))
        db.commit()

    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
