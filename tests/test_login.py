"""Тесты входа репетитора (`/tutor/login`)."""

from app.database import SessionLocal
from app.tutor.models.tutor import Tutor
from app.tutor.services.password_hasher import PasswordHasher
from app.tutor.services.sessions import COOKIE_NAME

PASSWORD = "Секретный-Пароль-1"


def _register(client, email="login-user@example.com", name="Входящий"):
    return client.post(
        "/tutor/register",
        data={"name": name, "email": email, "password": PASSWORD, "password_confirm": PASSWORD},
    )


def test_get_renders_form(client):
    response = client.get("/tutor/login")
    assert response.status_code == 200
    assert "Вход" in response.text


def test_registered_notice_shown(client):
    response = client.get("/tutor/login?registered=1")
    assert response.status_code == 200
    assert "Аккаунт создан" in response.text


def test_successful_login_sets_cookie_and_redirects(client):
    _register(client)

    response = client.post(
        "/tutor/login",
        data={"email": "login-user@example.com", "password": PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/"
    assert COOKIE_NAME in response.cookies

    cookie = response.cookies[COOKIE_NAME]
    assert cookie  # токен непустой


def test_session_cookie_is_httponly(client):
    """Cookie сессии — httpOnly и SameSite=Lax (защита от JS-доступа и CSRF)."""
    _register(client)
    response = client.post(
        "/tutor/login",
        data={"email": "login-user@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    headers = response.headers.get_list("set-cookie")
    joined = ";".join(headers).lower()
    assert "httponly" in joined
    assert "samesite=lax" in joined


def test_wrong_password_rejected(client):
    _register(client)
    response = client.post(
        "/tutor/login",
        data={"email": "login-user@example.com", "password": "неверный"},
    )
    assert response.status_code == 200
    assert "Неверный email или пароль" in response.text
    assert COOKIE_NAME not in response.cookies


def test_unknown_email_rejected(client):
    _register(client)
    response = client.post(
        "/tutor/login",
        data={"email": "nikto@example.com", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert "Неверный email или пароль" in response.text
    assert COOKIE_NAME not in response.cookies


def test_error_message_identical_for_both_reasons(client):
    """Неизвестный email и неверный пароль дают одинаковое сообщение."""
    _register(client)

    unknown = client.post(
        "/tutor/login",
        data={"email": "nikto@example.com", "password": PASSWORD},
    )
    wrong = client.post(
        "/tutor/login",
        data={"email": "login-user@example.com", "password": "неверный"},
    )

    def error_text(html: str) -> str:
        start = html.index('class="error"')
        end = html.index("</p>", start)
        return html[start:end]

    assert error_text(unknown.text) == error_text(wrong.text)


def test_migrated_tutor_without_password_cannot_login(client, tutor_factory):
    """Строки из миграции без пароля не могут войти, а не падают 500."""
    tutor_factory(email="migrated@example.com", name="Мигрированный")
    response = client.post(
        "/tutor/login",
        data={"email": "migrated@example.com", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert "Неверный email или пароль" in response.text


def test_login_with_correct_hashed_password(client, tutor_factory):
    """Фабричная запись с реальным хешем входит по паролю."""
    tutor_factory(email="hash-user@example.com", password=PASSWORD)
    response = client.post(
        "/tutor/login",
        data={"email": "hash-user@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert COOKIE_NAME in response.cookies


def test_password_hash_not_leaked_on_login_page(client):
    """Ни хеш, ни открытый пароль не попадают в HTML форм."""
    _register(client)
    with SessionLocal() as db:
        tutor = db.query(Tutor).filter_by(email="login-user@example.com").one()
        stored = tutor.password_hash
    response = client.get("/tutor/login")
    assert stored not in response.text
    assert PASSWORD not in response.text


def test_hasher_used_for_registration(client):
    """Пароль, созданный регистрацией, реально проверяется хешером."""
    _register(client)
    with SessionLocal() as db:
        tutor = db.query(Tutor).filter_by(email="login-user@example.com").one()
    assert PasswordHasher().verify(PASSWORD, tutor.password_hash) is True
    assert PasswordHasher().verify("другой", tutor.password_hash) is False
