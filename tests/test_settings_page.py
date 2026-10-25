"""Тесты страницы настройки мессенджеров (`/tutor/settings`).

Поведение через HTTP тем же путём, что у пользователя: те же маршруты и
поля формы, разметка ищется по тексту и атрибутам.
"""

from sqlalchemy import text

from app.database import SessionLocal
from app.messenger.services.connections import connected_messengers
from app.messenger.services.messengers import token_key

PASSWORD = "Секретный-Пароль-1"
TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
MAX_TOKEN = "pKcfaXfFUnfTSMPSYJjpdHHnPEMucRQGxFYEXhIq"


def _register_and_login(client, email):
    client.post(
        "/tutor/register",
        data={
            "name": "Настройки Мессенджеров",
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


def _login(client, email="messenger-user@example.com"):
    return _register_and_login(client, email=email)


def _param_count(tutor_id, key=token_key("telegram")):
    with SessionLocal() as db:
        return db.execute(
            text("select count(*) from tutor_params where tutor_id = :t and key = :k"),
            {"t": tutor_id, "k": key},
        ).scalar()


def _tutor_id_by_email(email):
    with SessionLocal() as db:
        return db.execute(
            text("select id from tutors where email = :e"),
            {"e": email},
        ).scalar()


# ---------------------------------------------------------------------------
# Доступ
# ---------------------------------------------------------------------------


def test_get_redirects_to_login_without_session(client):
    response = client.get("/tutor/settings", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_post_redirects_to_login_without_session(client):
    response = client.post(
        "/tutor/settings/messengers", data={"telegram_token": TOKEN},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


# ---------------------------------------------------------------------------
# Вкладка «Мессенджеры»
# ---------------------------------------------------------------------------


def test_page_renders_messengers_tab(client):
    _login(client)
    response = client.get("/tutor/settings")
    assert response.status_code == 200
    assert "Мессенджеры" in response.text
    # Активна вкладка «Мессенджеры»: только у неё aria-current.
    assert 'aria-current="page"' in response.text
    assert "/tutor/settings?tab=messengers" in response.text
    # Секция Telegram с полем токена.
    assert "Telegram" in response.text
    assert 'name="telegram_token"' in response.text
    # Пока токена нет — статус «Не подключён».
    assert "Не подключён" in response.text


def test_page_shows_max_field_and_pending_vk_without_fields(client):
    """MAX поддерживается и получает поле токена; VK — заготовка «Скоро»."""
    _login(client)
    response = client.get("/tutor/settings")
    assert "MAX" in response.text
    assert 'name="max_token"' in response.text
    assert "Скоро" in response.text
    assert 'name="vk_token"' not in response.text


def test_sidebar_menu_points_to_settings(client):
    _login(client)
    response = client.get("/tutor/settings")
    assert 'href="/tutor/settings"' in response.text


def test_connected_status_shown_after_save(client):
    _login(client)
    client.post("/tutor/settings/messengers", data={"telegram_token": TOKEN})
    response = client.get("/tutor/settings")
    assert "Подключён" in response.text
    # Токен подставлен обратно в поле.
    assert f'value="{TOKEN}"' in response.text


# ---------------------------------------------------------------------------
# Сохранение токена
# ---------------------------------------------------------------------------


def test_save_token(client):
    _login(client)
    response = client.post(
        "/tutor/settings/messengers",
        data={"telegram_token": TOKEN},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/settings?tab=messengers&saved=1"

    tutor_id = _tutor_id_by_email("messenger-user@example.com")
    assert _param_count(tutor_id) == 1
    # Плашка об успешном сохранении — на странице после редиректа.
    page = client.get(response.headers["location"])
    assert "Изменения сохранены" in page.text


def test_save_token_extracted_from_bot_url(client):
    """Вставка полной ссылки на бота: токен извлекается из неё."""
    _login(client)
    client.post(
        "/tutor/settings/messengers",
        data={"telegram_token": f"https://api.telegram.org/bot{TOKEN}"},
    )
    with SessionLocal() as db:
        value = db.execute(
            text("select value from tutor_params where key = 'telegram_token'"),
        ).scalar()
    assert value == TOKEN


def test_save_invalid_token_shows_error(client):
    _login(client)
    response = client.post(
        "/tutor/settings/messengers", data={"telegram_token": "просто-строка"},
    )
    assert response.status_code == 200
    assert "Токен Telegram должен быть" in response.text

    tutor_id = _tutor_id_by_email("messenger-user@example.com")
    assert _param_count(tutor_id) == 0


def test_empty_token_disconnects(client):
    """Пустое поле при сохранённом токене удаляет подключение."""
    _login(client)
    client.post("/tutor/settings/messengers", data={"telegram_token": TOKEN})
    response = client.post(
        "/tutor/settings/messengers", data={"telegram_token": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/settings?tab=messengers&saved=1"

    tutor_id = _tutor_id_by_email("messenger-user@example.com")
    assert _param_count(tutor_id) == 0
    page = client.get("/tutor/settings")
    assert "Не подключён" in page.text


def test_save_max_token(client):
    _login(client)
    response = client.post(
        "/tutor/settings/messengers",
        data={"max_token": MAX_TOKEN},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/settings?tab=messengers&saved=1"

    tutor_id = _tutor_id_by_email("messenger-user@example.com")
    assert _param_count(tutor_id, token_key("max")) == 1

    page = client.get("/tutor/settings?tab=messengers&saved=1")
    assert "Изменения сохранены" in page.text
    # Статусы независимы: MAX подключён, Telegram — нет.
    assert page.text.count("Подключён") == 1
    assert "Не подключён" in page.text


def test_save_both_tokens_at_once(client):
    _login(client)
    client.post(
        "/tutor/settings/messengers",
        data={"telegram_token": TOKEN, "max_token": MAX_TOKEN},
    )
    tutor_id = _tutor_id_by_email("messenger-user@example.com")
    assert _param_count(tutor_id, token_key("telegram")) == 1
    assert _param_count(tutor_id, token_key("max")) == 1


def test_save_invalid_max_token_shows_error(client):
    _login(client)
    response = client.post(
        "/tutor/settings/messengers", data={"max_token": "просто-строка"},
    )
    assert response.status_code == 200
    assert "Токен MAX должен быть" in response.text

    tutor_id = _tutor_id_by_email("messenger-user@example.com")
    assert _param_count(tutor_id, token_key("max")) == 0


def test_save_mixed_with_invalid_max_saves_nothing(client):
    """Хоть один токен невалиден — сохранения не происходит вовсе."""
    _login(client)
    client.post(
        "/tutor/settings/messengers",
        data={"telegram_token": TOKEN, "max_token": "bad"},
    )
    tutor_id = _tutor_id_by_email("messenger-user@example.com")
    assert _param_count(tutor_id, token_key("telegram")) == 0
    assert _param_count(tutor_id, token_key("max")) == 0


# ---------------------------------------------------------------------------
# Изоляция по репетитору
# ---------------------------------------------------------------------------


def test_token_is_isolated_by_tutor(client, tutor_factory):
    """Токен репетитора A не делает подключённым репетитора B."""
    tutor_factory(email="other@example.com", password=PASSWORD)
    _login(client)  # messenger-user@example.com
    client.post("/tutor/settings/messengers", data={"telegram_token": TOKEN})

    with SessionLocal() as db:
        assert connected_messengers(db, _tutor_id_by_email("other@example.com")) == []
        assert connected_messengers(
            db, _tutor_id_by_email("messenger-user@example.com")
        ) == ["telegram"]

    # Вход вторым репетитором: его страница показывает «Не подключён».
    client.post("/tutor/login", data={"email": "other@example.com", "password": PASSWORD})
    page = client.get("/tutor/settings")
    assert "Не подключён" in page.text
    assert f'value="{TOKEN}"' not in page.text
