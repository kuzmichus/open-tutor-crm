"""Тесты режима работы CRM: сингл и мульти (`SINGLE_MODE`).

Сингл-режим нужен персональной установке: аккаунт один, а страница
регистрации живёт только до его создания. После первого запуска она
отвечает 404 и на GET, и на POST, а вход перестаёт отправлять на неё.
Мульти-режим — прежнее поведение: регистрация открыта всегда.
"""

import pytest

from app.config import Settings, settings
from app.database import SessionLocal
from app.tutor.models.tutor import Tutor

PASSWORD = "Секретный-Пароль-1"

FORM = {
    "name": "Единственный Репетитор",
    "email": "single@example.com",
    "password": PASSWORD,
    "password_confirm": PASSWORD,
}


@pytest.fixture()
def single_mode(monkeypatch):
    """Включает сингл-режим на время теста."""
    monkeypatch.setattr(settings, "single_mode", True)
    return settings


def _tutor_count() -> int:
    with SessionLocal() as db:
        return db.query(Tutor).count()


def _register(client, email: str = "single@example.com", name: str = "Репетитор"):
    return client.post(
        "/tutor/register",
        data={
            "name": name,
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
        follow_redirects=False,
    )


# --------------------------------------------------------------------------
# Конфигурация
# --------------------------------------------------------------------------

def test_default_mode_is_multi(monkeypatch):
    """Без SINGLE_MODE установка работает в мульти-режиме.

    `_env_file=None` отключает .env, но не реальное окружение: conftest
    задаёт SINGLE_MODE для герметичности прогона, здесь его снимаем.
    """
    monkeypatch.delenv("SINGLE_MODE", raising=False)
    assert Settings(_env_file=None).single_mode is False


def test_env_overrides_single_mode(monkeypatch):
    """SINGLE_MODE=true из окружения включает сингл-режим."""
    monkeypatch.setenv("SINGLE_MODE", "true")
    assert Settings(_env_file=None).single_mode is True


# --------------------------------------------------------------------------
# Мульти-режим: поведение не меняется
# --------------------------------------------------------------------------

def test_multi_mode_registration_is_always_open(client, tutor_factory):
    """В мульти-режиме регистрация доступна и при существующих репетиторах."""
    tutor_factory()

    assert client.get("/tutor/register").status_code == 200
    assert _register(client).status_code == 303
    assert _tutor_count() == 2


def test_multi_mode_login_does_not_redirect(client):
    """В мульти-режиме пустая база не отправляет вход на регистрацию."""
    response = client.get("/tutor/login", follow_redirects=False)
    assert response.status_code == 200
    assert "Вход" in response.text


def test_multi_mode_shows_registration_link(client):
    """В мульти-режиме ссылка «Зарегистрироваться» остаётся на месте."""
    page = client.get("/tutor/login").text
    assert 'href="/tutor/register"' in page


# --------------------------------------------------------------------------
# Сингл-режим: первый запуск
# --------------------------------------------------------------------------

def test_single_mode_first_run_opens_registration(client, single_mode):
    """Пока репетиторов нет, форма регистрации доступна."""
    response = client.get("/tutor/register")
    assert response.status_code == 200
    assert "Регистрация репетитора" in response.text


def test_single_mode_first_run_login_redirects_to_registration(client, single_mode):
    """На первом запуске вход ведёт на регистрацию единственного аккаунта."""
    response = client.get("/tutor/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/register"

    follow = client.get(response.headers["location"])
    assert follow.status_code == 200
    assert "Регистрация репетитора" in follow.text


def test_single_mode_first_run_root_leads_to_registration(client, single_mode):
    """Цепочка `/` → `/tutor/` → вход → регистрация доходит до формы."""
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert "Регистрация репетитора" in response.text


def test_single_mode_first_registration_creates_tutor(client, single_mode):
    """Первый запуск позволяет создать единственный аккаунт."""
    response = _register(client, name="Единственный Репетитор")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/tutor/login")

    with SessionLocal() as db:
        tutor = db.query(Tutor).filter_by(email="single@example.com").one()
        assert tutor.name == "Единственный Репетитор"
    assert _tutor_count() == 1


# --------------------------------------------------------------------------
# Сингл-режим: регистрация закрыта после первого аккаунта
# --------------------------------------------------------------------------

def test_single_mode_registration_get_is_404_when_tutor_exists(
    client, single_mode, tutor_factory
):
    """После первого аккаунта GET страницы регистрации — 404."""
    tutor_factory()

    response = client.get("/tutor/register")
    assert response.status_code == 404
    # Кастомная страница, а не стандартный JSON/Not Found.
    assert "404" in response.text


def test_single_mode_registration_post_is_404_when_tutor_exists(
    client, single_mode, tutor_factory
):
    """POST в обход формы тоже не создаёт второго репетитора."""
    tutor_factory()
    before = _tutor_count()

    response = _register(client, email="second@example.com", name="Второй")
    assert response.status_code == 404
    assert _tutor_count() == before


def test_single_mode_registration_closed_right_after_registration(client, single_mode):
    """После успешной регистрации страница недоступна и по GET, и по POST."""
    assert _register(client).status_code == 303

    assert client.get("/tutor/register").status_code == 404
    response = _register(client, email="another@example.com", name="Ещё один")
    assert response.status_code == 404
    assert _tutor_count() == 1


def test_single_mode_login_works_after_first_registration(client, single_mode):
    """Когда аккаунт уже есть, вход показывает обычную форму без редиректа."""
    _register(client)

    response = client.get("/tutor/login", follow_redirects=False)
    assert response.status_code == 200
    assert "Вход" in response.text


def test_single_mode_hides_registration_link_when_closed(
    client, single_mode, tutor_factory
):
    """Ссылка на закрытую регистрацию не показывается — она вела бы в 404."""
    tutor_factory()

    login = client.get("/tutor/login").text
    assert 'href="/tutor/register"' not in login

    remember = client.get("/tutor/remember-password").text
    assert 'href="/tutor/register"' not in remember


def test_single_mode_shows_registration_link_on_first_run(client, single_mode):
    """На первом запуске ссылка на регистрацию остаётся доступной."""
    # Вход редиректит, поэтому проверяем страницу восстановления пароля:
    # она доступна на первом запуске и тоже содержит ссылку на регистрацию.
    page = client.get("/tutor/remember-password").text
    assert 'href="/tutor/register"' in page
