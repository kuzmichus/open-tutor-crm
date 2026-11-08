"""Тесты управляющей страницы лендинга и шаблона по умолчанию.

Проверяются: доступ (сессия и сингл-режим), генерация черновика из профиля,
экранирование полей, предпросмотр, публикация и снятие с публикации.
Публичная отдача `/` и ассетов живёт в `tests/test_landing_public.py`.
"""

from decimal import Decimal

import pytest

from app.config import settings
from app.landing.services.storage import LandingStorage

PASSWORD = "Секретный-Пароль-1"
EMAIL = "landing-owner@example.com"


@pytest.fixture()
def landing_root(tmp_path, monkeypatch):
    """Изолированный каталог лендинга на время теста."""
    root = tmp_path / "landing"
    monkeypatch.setattr(settings, "landing_root", str(root))
    return root


@pytest.fixture()
def single_mode(monkeypatch):
    """Включает сингл-режим: фича лендинга доступна."""
    monkeypatch.setattr(settings, "single_mode", True)


def _login(client, email=EMAIL):
    return client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )


@pytest.fixture()
def owner(client, tutor_factory, landing_root, single_mode):
    """Репетитор с заполненным профилем, вошедший в клиент."""
    tutor_id = tutor_factory(
        name="Анна Иванова",
        email=EMAIL,
        password=PASSWORD,
        subject="математике",
        about="Готовлю к экзаменам и объясняю сложное простыми словами.",
        experience="8 лет",
        hourly_rate=Decimal("1200"),
        phone="+7 (999) 123-45-67",
    )
    _login(client)
    return tutor_id


def _page_html(client):
    response = client.get("/tutor/landing")
    assert response.status_code == 200
    return response.text


# --------------------------------------------------------------------------
# Доступ
# --------------------------------------------------------------------------


def test_page_requires_login(client, landing_root, single_mode):
    """Без сессии страница управления ведёт на вход."""
    response = client.get("/tutor/landing", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_routes_are_not_found_in_multi_mode(client, tutor_factory, landing_root):
    """В мульти-режиме все роуты лендинга отвечают 404."""
    tutor_factory(email=EMAIL, password=PASSWORD)
    _login(client)

    assert client.get("/tutor/landing").status_code == 404
    assert client.get("/tutor/landing/preview").status_code == 404
    for url in (
        "/tutor/landing/publish",
        "/tutor/landing/unpublish",
        "/tutor/landing/reset",
    ):
        assert client.post(url).status_code == 404, url
    # Ничего не создано на диске.
    assert not (landing_root / "draft.html").exists()
    assert not (landing_root / "index.html").exists()


def test_two_tutors_do_not_unlock_landing_in_multi_mode(
    client, tutor_factory, landing_root
):
    """Даже при нескольких репетиторах в мульти-режиме лендинга нет."""
    tutor_factory(email="first-landing@example.com", password=PASSWORD)
    tutor_factory(email=EMAIL, password=PASSWORD)
    _login(client)

    assert client.get("/tutor/landing").status_code == 404


# --------------------------------------------------------------------------
# Пустое состояние
# --------------------------------------------------------------------------


def test_empty_state_shows_create_button(client, owner, landing_root):
    """Без черновика страница показывает «Пусто» и создание черновика."""
    page = _page_html(client)

    assert "Пусто" in page
    assert "Создать черновик" in page
    assert "Предпросмотр" not in page
    assert "Опубликовать" not in page
    assert not (landing_root / "draft.html").exists()


def test_publish_without_draft_does_nothing(client, owner, landing_root):
    """Публиковать нечего — редирект с подсказкой, `index.html` не создан."""
    response = client.post("/tutor/landing/publish", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/landing?status=no-draft"
    assert not (landing_root / "index.html").exists()


# --------------------------------------------------------------------------
# Генерация черновика из профиля
# --------------------------------------------------------------------------


def test_reset_creates_draft_from_profile(client, owner, landing_root):
    """«Создать черновик» рендерит шаблон данными профиля."""
    response = client.post("/tutor/landing/reset", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/landing?status=reset"

    draft = (landing_root / "draft.html").read_text(encoding="utf-8")
    assert "Анна Иванова" in draft
    assert "математике" in draft
    assert "Готовлю к экзаменам" in draft
    assert "8 лет" in draft
    assert "1\u00a0200\u00a0₽" in draft
    assert "+7 (999) 123-45-67" in draft
    assert f"<title>Анна Иванова — репетитор по математике</title>" in draft
    assert f'href="/s/{owner}"' in draft


def test_template_has_login_entries_and_no_external_assets(client, owner, landing_root):
    """В шаблоне есть точки входа, локальный скрипт и нет CDN/app.css."""
    client.post("/tutor/landing/reset")
    draft = (landing_root / "draft.html").read_text(encoding="utf-8")

    assert 'href="/student/login" data-auth="student"' in draft
    assert 'href="/parent/login" data-auth="parent"' in draft
    assert 'href="/tutor/login" data-auth="tutor"' in draft
    assert '<script src="/static/landing-auth.js" defer></script>' in draft
    assert "styles.css" not in draft
    assert "app.css" not in draft
    assert "https://" not in draft
    assert "http://" not in draft
    # Мобильный брейкпоинт.
    assert "@media (max-width: 640px)" in draft


def test_profile_fields_are_escaped(client, tutor_factory, landing_root, single_mode):
    """`<script>` из профиля не становится исполняемым тегом."""
    tutor_factory(
        name="Вредный",
        email=EMAIL,
        password=PASSWORD,
        subject="физике",
        about="<script>alert(1)</script>",
    )
    _login(client)

    client.post("/tutor/landing/reset")
    draft = (landing_root / "draft.html").read_text(encoding="utf-8")

    assert "<script>alert(1)</script>" not in draft
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in draft


def test_get_does_not_overwrite_draft(client, owner, landing_root):
    """Обычный просмотр страницы не трогает правки черновика."""
    storage = LandingStorage(landing_root)
    storage.save_draft("<html><body>Ручная правка</body></html>")

    _page_html(client)
    assert storage.read_draft_html() == "<html><body>Ручная правка</body></html>"

    client.post("/tutor/landing/reset")
    assert "Ручная правка" not in storage.read_draft_html()
    assert "Анна Иванова" in storage.read_draft_html()


# --------------------------------------------------------------------------
# Предпросмотр
# --------------------------------------------------------------------------


def test_preview_without_draft_is_not_found(client, owner):
    assert client.get("/tutor/landing/preview").status_code == 404


def test_preview_serves_draft(client, owner, landing_root):
    """Предпросмотр отдаёт черновик как есть, без кэша."""
    html = "<!doctype html><html><body><h1>Черновик</h1></body></html>"
    LandingStorage(landing_root).save_draft(html)

    response = client.get("/tutor/landing/preview")

    assert response.status_code == 200
    assert response.text == html
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"


# --------------------------------------------------------------------------
# Публикация и снятие
# --------------------------------------------------------------------------


def test_publish_makes_page_public(client, owner, landing_root):
    """Публикация копирует черновик в `index.html`, и `/` отдаёт страницу."""
    client.post("/tutor/landing/reset")
    draft = (landing_root / "draft.html").read_text(encoding="utf-8")

    response = client.post("/tutor/landing/publish", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/landing?status=published"
    assert (landing_root / "index.html").read_text(encoding="utf-8") == draft

    root = client.get("/", follow_redirects=False)
    assert root.status_code == 200
    assert 'href="/student/login"' in root.text
    assert 'href="/parent/login"' in root.text
    assert 'href="/tutor/login"' in root.text
    assert f'href="/s/{owner}"' in root.text
    assert root.headers["cache-control"] == "no-cache"


def test_second_publish_writes_backup(client, owner, landing_root):
    """Повторная публикация кладёт прошлую версию в `index.prev.html`."""
    client.post("/tutor/landing/reset")
    client.post("/tutor/landing/publish")
    first = (landing_root / "index.html").read_text(encoding="utf-8")

    LandingStorage(landing_root).save_draft("<html><body>Вторая версия</body></html>")
    client.post("/tutor/landing/publish")

    assert (landing_root / "index.html").read_text(encoding="utf-8") == (
        "<html><body>Вторая версия</body></html>"
    )
    assert (landing_root / "index.prev.html").read_text(encoding="utf-8") == first


def test_unpublish_removes_page_but_keeps_draft_and_backup(
    client, owner, landing_root
):
    """Снятие с публикации: `/` снова 303, черновик и бэкап целы."""
    client.post("/tutor/landing/reset")
    client.post("/tutor/landing/publish")
    client.post("/tutor/landing/publish")
    prev = (landing_root / "index.prev.html").read_text(encoding="utf-8")
    draft = (landing_root / "draft.html").read_text(encoding="utf-8")

    response = client.post("/tutor/landing/unpublish", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/landing?status=unpublished"
    assert not (landing_root / "index.html").exists()
    assert (landing_root / "draft.html").read_text(encoding="utf-8") == draft
    assert (landing_root / "index.prev.html").read_text(encoding="utf-8") == prev

    root = client.get("/", follow_redirects=False)
    assert root.status_code == 303
    assert root.headers["location"] == "/tutor/"


def test_page_shows_published_status(client, owner, landing_root):
    """После публикации страница управления показывает статус «Опубликован»."""
    client.post("/tutor/landing/reset")
    client.post("/tutor/landing/publish")

    page = _page_html(client)
    assert "Опубликован" in page
    assert "Снять с публикации" in page


def test_page_shows_draft_status(client, owner):
    """После создания черновика без публикации — статус «Черновик»."""
    client.post("/tutor/landing/reset")

    page = _page_html(client)
    assert "Черновик" in page
    assert "Предпросмотр" in page
    assert "Вернуть шаблон" in page
