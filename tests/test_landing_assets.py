"""Тесты загрузки и удаления картинок лендинга (спека `landing-page`).

Проверяются оба управляющих роута (`POST`/`DELETE /tutor/landing/assets`),
инициализация Asset Manager в редакторе и ограничения: только картинки,
лимит размера, магические байты растров, сессия репетитора и сингл-режим.
Публичная отдача ассетов живёт в `test_landing_public.py`.
"""

import json
import re
from decimal import Decimal

import pytest
from app.config import settings
from app.landing.services.storage import LandingStorage, is_asset_name

PASSWORD = "Секретный-Пароль-1"
EMAIL = "landing-assets@example.com"

PNG = b"\x89PNG\r\n\x1a\n" + b"payload"
JPEG = b"\xff\xd8\xff\xe0" + b"payload"
GIF = b"GIF89a" + b"payload"
WEBP = b"RIFF\x10\x00\x00\x00WEBP" + b"payload"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'

IMAGE_CASES = [
    ("photo.png", b"\x89PNG\r\n\x1a\npayload", "image/png"),
    ("photo.jpg", b"\xff\xd8\xff\xe0payload", "image/jpeg"),
    ("photo.jpeg", b"\xff\xd8\xff\xe0payload", "image/jpeg"),
    ("photo.gif", b"GIF87apayload", "image/gif"),
    ("photo.webp", b"RIFF\x10\x00\x00\x00WEBPpayload", "image/webp"),
    ("photo.svg", SVG, "image/svg+xml"),
]


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
        about="Готовлю к экзаменам.",
        experience="8 лет",
        hourly_rate=Decimal("1200"),
        phone="+7 (999) 123-45-67",
    )
    _login(client)
    return tutor_id


def _upload(client, files, field="files"):
    """POST загрузки ассета: список `(имя, тело, тип)` в одном поле."""
    return client.post(
        "/tutor/landing/assets",
        files=[(field, item) for item in files],
    )


def _assets_dir(landing_root):
    return landing_root / "assets"


def _saved_names(landing_root):
    directory = _assets_dir(landing_root)
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.iterdir() if path.is_file())


def _editor_assets(response):
    """Достаёт JSON ассетов из `<script id="landing-assets">`."""
    match = re.search(
        r'<script type="application/json" id="landing-assets">(.*?)</script>',
        response.text,
        re.DOTALL,
    )
    assert match is not None, "JSON ассетов не найден в странице редактора"
    return json.loads(match.group(1))


# --------------------------------------------------------------------------
# Загрузка: успешные сценарии
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "content", "media_type"),
    IMAGE_CASES,
    ids=[case[0] for case in IMAGE_CASES],
)
def test_upload_saves_image(
    client, owner, landing_root, filename, content, media_type
):
    """Картинка сохраняется под uuid-именем и отдаётся публично."""
    response = _upload(client, [(filename, content, media_type)])

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["type"] == "image"
    src = data[0]["src"]
    assert src.startswith("/landing-assets/")

    name = src.removeprefix("/landing-assets/")
    assert is_asset_name(name)
    assert (landing_root / "assets" / name).read_bytes() == content

    served = client.get(src)
    assert served.status_code == 200
    assert served.content == content
    assert served.headers["content-type"] == media_type


def test_upload_accepts_files_field(client, owner, landing_root):
    """Поле `files` (multiUpload=false) принимается наравне с `files[]`."""
    response = _upload(client, [("photo.png", PNG, "image/png")], field="files")

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert len(_saved_names(landing_root)) == 1


def test_upload_accepts_files_array_field(client, owner, landing_root):
    """Поле `files[]` — имя, которое GrapesJS шлёт при multiUpload."""
    response = _upload(
        client, [("photo.png", PNG, "image/png")], field="files[]"
    )

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert len(_saved_names(landing_root)) == 1


def test_upload_accepts_multiple_files(client, owner, landing_root):
    """Несколько файлов в одном запросе — несколько ассетов в ответе."""
    response = _upload(
        client,
        [
            ("first.png", PNG, "image/png"),
            ("second.jpg", JPEG, "image/jpeg"),
        ],
        field="files[]",
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2
    assert all(item["type"] == "image" for item in data)
    assert len(_saved_names(landing_root)) == 2


def test_upload_does_not_overwrite_same_name(client, owner, landing_root):
    """Две загрузки `photo.png` дают два разных файла на диске."""
    first = _upload(client, [("photo.png", PNG, "image/png")]).json()["data"][0]
    second = _upload(client, [("photo.png", PNG, "image/png")]).json()["data"][0]

    assert first["src"] != second["src"]
    assert len(_saved_names(landing_root)) == 2


# --------------------------------------------------------------------------
# Загрузка: отказы
# --------------------------------------------------------------------------


def test_upload_without_files_is_400(client, owner):
    """Пустая форма — понятное сообщение, а не 500."""
    response = client.post("/tutor/landing/assets")

    assert response.status_code == 400
    assert response.json()["error"] == "Выберите файл для загрузки."


@pytest.mark.parametrize(
    "filename",
    ["virus.exe", "page.html", "script.js", "noext", "photo.php"],
    ids=["exe", "html", "js", "no-ext", "php"],
)
def test_upload_rejects_non_image_extension(client, owner, landing_root, filename):
    """Не-картинка отклоняется с понятным сообщением, диск не меняется."""
    response = _upload(client, [(filename, b"payload", "application/octet-stream")])

    assert response.status_code == 400
    assert (
        "недопустимый формат" in response.json()["error"]
        or "должен иметь расширение" in response.json()["error"]
    )
    assert _saved_names(landing_root) == []


def test_upload_rejects_text_masquerading_as_png(client, owner, landing_root):
    """`photo.png` с текстом внутри — не картинка (магические байты)."""
    response = _upload(
        client, [("photo.png", b"not really a png", "image/png")]
    )

    assert response.status_code == 400
    assert "не является картинкой" in response.json()["error"]
    assert _saved_names(landing_root) == []


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("photo.png", b"\xff\xd8\xff\xe0 jpeg bytes"),
        ("photo.jpg", b"\x89PNG\r\n\x1a\n png bytes"),
        ("photo.gif", b"RIFF\x10\x00\x00\x00WEBP webp bytes"),
        ("photo.webp", b"GIF89a gif bytes"),
    ],
    ids=["png-as-jpeg", "jpg-as-png", "gif-as-webp", "webp-as-gif"],
)
def test_upload_rejects_mismatched_signature(
    client, owner, landing_root, filename, content
):
    """Содержимое должно совпадать с расширением, а не только быть картинкой."""
    response = _upload(client, [(filename, content, "image/*")])

    assert response.status_code == 400
    assert "не является картинкой" in response.json()["error"]
    assert _saved_names(landing_root) == []


def test_upload_rejects_empty_file(client, owner, landing_root):
    """Пустой файл отклоняется: открыть его как картинку нельзя."""
    response = _upload(client, [("photo.png", b"", "image/png")])

    assert response.status_code == 400
    assert "пустой" in response.json()["error"]
    assert _saved_names(landing_root) == []


def test_upload_rejects_oversized_file(client, owner, landing_root, monkeypatch):
    """Файл больше `FILES_MAX_SIZE_MB` отклоняется с 413."""
    monkeypatch.setattr(settings, "files_max_size_mb", 1)

    response = _upload(
        client,
        [("big.png", b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024), "image/png")],
    )

    assert response.status_code == 413
    assert "больше 1 МБ" in response.json()["error"]
    assert _saved_names(landing_root) == []


def test_upload_rejects_whole_batch_if_one_file_invalid(client, owner, landing_root):
    """Валидный файл рядом с невалидным не сохраняется: набор атомарен."""
    response = _upload(
        client,
        [
            ("ok.png", PNG, "image/png"),
            ("virus.exe", b"MZ", "application/octet-stream"),
        ],
        field="files[]",
    )

    assert response.status_code == 400
    assert _saved_names(landing_root) == []


# --------------------------------------------------------------------------
# Удаление
# --------------------------------------------------------------------------


def test_delete_removes_file_and_link_is_404(client, owner, landing_root):
    """Удаление убирает файл с диска; ссылка на него — 404."""
    src = _upload(client, [("photo.png", PNG, "image/png")]).json()["data"][0]["src"]
    name = src.removeprefix("/landing-assets/")
    assert (landing_root / "assets" / name).is_file()

    response = client.delete(f"/tutor/landing/assets/{name}")

    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert not (landing_root / "assets" / name).exists()
    assert client.get(src).status_code == 404


def test_delete_is_idempotent(client, owner, landing_root):
    """Повторное удаление того же имени — не ошибка."""
    src = _upload(client, [("photo.png", PNG, "image/png")]).json()["data"][0]["src"]
    name = src.removeprefix("/landing-assets/")

    assert client.delete(f"/tutor/landing/assets/{name}").status_code == 204
    assert client.delete(f"/tutor/landing/assets/{name}").status_code == 204


@pytest.mark.parametrize(
    "name",
    [
        "photo.png",
        "not-a-uuid.png",
        "01234567-89ab-cdef-0123-456789abcdef.exe",
        "01234567-89ab-cdef-0123-456789abcdef.png.bak",
        "..%2Fsecret.png",
    ],
    ids=["plain", "not-uuid", "bad-ext", "double-ext", "traversal"],
)
def test_delete_rejects_foreign_name(client, owner, landing_root, name):
    """Невалидное имя — 404, посторонние файлы на диске целы."""
    storage = LandingStorage(landing_root)
    keep = storage.save_asset("keep.png", PNG)

    response = client.delete(f"/tutor/landing/assets/{name}")

    assert response.status_code == 404
    assert _saved_names(landing_root) == [keep]


# --------------------------------------------------------------------------
# Доступ
# --------------------------------------------------------------------------


def test_upload_requires_session(client, landing_root, single_mode):
    """Без сессии загрузка ведёт на вход и ничего не пишет."""
    response = client.post(
        "/tutor/landing/assets",
        files={"files": ("photo.png", PNG, "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert _saved_names(landing_root) == []


def test_delete_requires_session(client, owner, landing_root):
    """Без сессии удаление ведёт на вход и файл остаётся."""
    src = _upload(client, [("photo.png", PNG, "image/png")]).json()["data"][0]["src"]
    name = src.removeprefix("/landing-assets/")
    client.cookies.clear()

    response = client.delete(
        f"/tutor/landing/assets/{name}", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert (landing_root / "assets" / name).is_file()


def test_upload_is_404_in_multi_mode(client, tutor_factory, landing_root, monkeypatch):
    """В мульти-режиме загрузка отвечает 404 и не пишет на диск."""
    monkeypatch.setattr(settings, "single_mode", False)
    tutor_factory(email=EMAIL, password=PASSWORD)
    _login(client)

    response = _upload(client, [("photo.png", PNG, "image/png")])

    assert response.status_code == 404
    assert _saved_names(landing_root) == []


def test_delete_is_404_in_multi_mode(client, tutor_factory, landing_root, monkeypatch):
    """В мульти-режиме удаление отвечает 404 и не трогает диск."""
    monkeypatch.setattr(settings, "single_mode", False)
    tutor_factory(email=EMAIL, password=PASSWORD)
    _login(client)
    storage = LandingStorage(landing_root)
    name = storage.save_asset("keep.png", PNG)

    response = client.delete(f"/tutor/landing/assets/{name}")

    assert response.status_code == 404
    assert (landing_root / "assets" / name).is_file()


def test_asset_serving_stays_public(client, landing_root, monkeypatch):
    """Публичная отдача картинок не зависит от режима и сессии."""
    monkeypatch.setattr(settings, "single_mode", False)
    name = LandingStorage(landing_root).save_asset("photo.png", PNG)

    assert client.get(f"/landing-assets/{name}").status_code == 200


# --------------------------------------------------------------------------
# Asset Manager в редакторе
# --------------------------------------------------------------------------


def test_editor_lists_existing_assets(client, owner, landing_root):
    """Список ассетов вшивается в шаблон редактора абсолютными ссылками."""
    storage = LandingStorage(landing_root)
    name = storage.save_asset("photo.png", PNG)

    assets = _editor_assets(client.get("/tutor/landing/editor"))

    assert assets == [{"src": f"/landing-assets/{name}", "type": "image"}]


def test_editor_ignores_foreign_files_in_assets_dir(client, owner, landing_root):
    """Файл с посторонним именем в `assets/` в редактор не попадает."""
    storage = LandingStorage(landing_root)
    (landing_root / "assets").mkdir(parents=True)
    (landing_root / "assets" / "notes.txt").write_text("x", encoding="utf-8")
    name = storage.save_asset("photo.png", PNG)

    assets = _editor_assets(client.get("/tutor/landing/editor"))

    assert [item["src"] for item in assets] == [f"/landing-assets/{name}"]


def test_editor_configures_asset_manager(client, owner):
    """В конфиге GrapesJS есть загрузка, список ассетов и удаление."""
    page = client.get("/tutor/landing/editor").text

    assert 'id="landing-assets"' in page
    assert "assetManager:" in page
    assert "upload: assetsUrl" in page
    assert "'/tutor/landing/assets'" in page
    assert "uploadName: 'files'" in page
    assert "assets: assets" in page
    assert "asset:remove" in page
    assert "method: 'DELETE'" in page
    assert "Загрузить изображение" in page
    assert "/landing-assets/" in page
