"""Тесты публичной части лендинга: `GET /` и `GET /landing-assets/...`.

Корень отдаёт опубликованный файл только в сингл-режиме и только когда
страница опубликована; иначе — прежний 303 на `/tutor/`. Ассеты публичны,
имя проверяется строгим шаблоном, кэш долгий.
"""

import pytest

from app.config import settings
from app.landing.services.storage import LandingStorage

PAGE = "<!doctype html><html><body><h1>Лендинг репетитора</h1></body></html>"


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


def _publish(root):
    """Публикует страницу и возвращает хранилище."""
    storage = LandingStorage(root)
    storage.save_draft(PAGE)
    storage.publish()
    return storage


# --------------------------------------------------------------------------
# Корень: редирект без публикации
# --------------------------------------------------------------------------

def test_root_redirects_in_multi_mode(client, landing_root, monkeypatch):
    """В мульти-режиме даже опубликованная страница не перехватывает `/`."""
    monkeypatch.setattr(settings, "single_mode", False)
    _publish(landing_root)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/"


def test_root_redirects_without_publication(client, landing_root, single_mode):
    """Сингл-режим без публикации — прежний 303 на `/tutor/`."""
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/"


def test_root_redirects_after_unpublish(client, landing_root, single_mode):
    """После `unpublish()` корень снова отвечает 303."""
    storage = _publish(landing_root)
    assert client.get("/", follow_redirects=False).status_code == 200

    storage.unpublish()

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/"


# --------------------------------------------------------------------------
# Корень: опубликованная страница
# --------------------------------------------------------------------------

def test_root_serves_published_page(client, landing_root, single_mode):
    """С `index.html` корень отдаёт файл как есть, без рендера."""
    _publish(landing_root)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert response.text == PAGE
    assert response.headers["content-type"].startswith("text/html")


def test_root_page_is_not_cached(client, landing_root, single_mode):
    """`Cache-Control: no-cache` — свежая публикация видна сразу."""
    _publish(landing_root)

    response = client.get("/")

    assert response.headers["cache-control"] == "no-cache"


def test_root_serves_latest_publication(client, landing_root, single_mode):
    """После повторной публикации корень отдаёт новую версию."""
    storage = _publish(landing_root)
    storage.save_draft("<h1>Новая версия</h1>")
    storage.publish()

    response = client.get("/")

    assert response.text == "<h1>Новая версия</h1>"


def test_root_does_not_serve_draft(client, landing_root, single_mode):
    """Черновик без публикации наружу не отдаётся."""
    LandingStorage(landing_root).save_draft(PAGE)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303


def test_root_serves_script_tags(client, landing_root, single_mode):
    """`<script>` на опубликованной странице разрешён и не вырезается."""
    storage = LandingStorage(landing_root)
    storage.save_draft("<html><script>window.landing=1;</script></html>")
    storage.publish()

    response = client.get("/")

    assert "<script>window.landing=1;</script>" in response.text


# --------------------------------------------------------------------------
# Ассеты
# --------------------------------------------------------------------------

def test_asset_is_served_with_long_cache(client, landing_root):
    """Картинка отдаётся публично, с типом по расширению и долгим кэшем."""
    name = LandingStorage(landing_root).save_asset("photo.png", b"\x89PNG-data")

    response = client.get(f"/landing-assets/{name}")

    assert response.status_code == 200
    assert response.content == b"\x89PNG-data"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


@pytest.mark.parametrize(
    ("filename", "media_type"),
    [
        ("a.jpg", "image/jpeg"),
        ("a.jpeg", "image/jpeg"),
        ("a.gif", "image/gif"),
        ("a.webp", "image/webp"),
        ("a.svg", "image/svg+xml"),
    ],
)
def test_asset_media_type_by_extension(client, landing_root, filename, media_type):
    """Тип содержимого соответствует расширению картинки."""
    name = LandingStorage(landing_root).save_asset(filename, b"data")

    response = client.get(f"/landing-assets/{name}")

    assert response.status_code == 200
    assert response.headers["content-type"] == media_type


def test_asset_is_public_in_multi_mode(client, landing_root, monkeypatch):
    """Картинки публичны независимо от режима: они часть страницы."""
    monkeypatch.setattr(settings, "single_mode", False)
    name = LandingStorage(landing_root).save_asset("photo.png", b"data")

    assert client.get(f"/landing-assets/{name}").status_code == 200


@pytest.mark.parametrize(
    "name",
    [
        "photo.png",
        "not-a-uuid.png",
        "01234567-89ab-cdef-0123-456789abcdef.exe",
        "01234567-89ab-cdef-0123-456789abcdef",
        "..%2Fsecret.png",
        "01234567-89ab-cdef-0123-456789abcdef.png.bak",
    ],
    ids=["plain", "not-uuid", "bad-ext", "no-ext", "traversal", "double-ext"],
)
def test_foreign_asset_name_is_404(client, landing_root, name):
    """Произвольное имя ассета — 404, файл на диске не ищется."""
    response = client.get(f"/landing-assets/{name}")

    assert response.status_code == 404


def test_missing_asset_is_404(client, landing_root):
    """Сгенерированное, но отсутствующее имя — 404."""
    name = "01234567-89ab-cdef-0123-456789abcdef.png"

    assert client.get(f"/landing-assets/{name}").status_code == 404


def test_removed_asset_is_404(client, landing_root):
    """Удалённый ассет больше не отдаётся."""
    storage = LandingStorage(landing_root)
    name = storage.save_asset("photo.png", b"data")
    assert client.get(f"/landing-assets/{name}").status_code == 200

    storage.remove_asset(name)

    assert client.get(f"/landing-assets/{name}").status_code == 404
