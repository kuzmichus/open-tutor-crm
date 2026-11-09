"""Тесты дискового хранилища лендинга (`app/landing/services/storage.py`).

Веб здесь не участвует: проверяются пути, ленивое создание каталогов,
публикация с бэкапом, отмена публикации и генерация имён ассетов. Корень —
`tmp_path`, как и в остальных тестах файловых хранилищ.
"""

import pytest

from app.config import Settings
from app.landing.services.storage import (
    ALLOWED_ASSET_EXTENSIONS,
    LandingStorage,
    is_asset_name,
    is_valid_asset_content,
)

# --------------------------------------------------------------------------
# Пустой корень: чтения отвечают «нет», каталоги не создаются
# --------------------------------------------------------------------------

def test_empty_root_has_no_draft_and_no_publication(tmp_path):
    """На пустом корне чтения отвечают «нет» без исключений."""
    storage = LandingStorage(tmp_path / "landing")

    assert storage.has_draft() is False
    assert storage.has_published() is False
    assert storage.read_draft_html() is None
    assert storage.list_assets() == []


def test_reads_do_not_create_root(tmp_path):
    """Чтения не создают каталог: установка без лендинга ничего не пишет."""
    root = tmp_path / "landing"
    storage = LandingStorage(root)

    storage.has_draft()
    storage.has_published()
    storage.read_draft_html()
    storage.list_assets()

    assert not root.exists()


def test_paths_live_under_root(tmp_path):
    """Раскладка каталога: draft/index/index.prev и assets/."""
    storage = LandingStorage(tmp_path)

    assert storage.draft_path == tmp_path / "draft.html"
    assert storage.index_path == tmp_path / "index.html"
    assert storage.prev_path == tmp_path / "index.prev.html"
    assert storage.assets_dir == tmp_path / "assets"


# --------------------------------------------------------------------------
# Черновик
# --------------------------------------------------------------------------

def test_save_and_read_draft_creates_root(tmp_path):
    """Сохранение черновика создаёт корень и читается обратно как UTF-8."""
    root = tmp_path / "nested" / "landing"
    storage = LandingStorage(root)

    storage.save_draft("<h1>Привет</h1>")

    assert root.is_dir()
    assert storage.has_draft() is True
    assert storage.read_draft_html() == "<h1>Привет</h1>"


def test_save_draft_overwrites_previous_version(tmp_path):
    """Повторное сохранение заменяет черновик целиком."""
    storage = LandingStorage(tmp_path)

    storage.save_draft("старый")
    storage.save_draft("новый")

    assert storage.read_draft_html() == "новый"


def test_save_draft_leaves_no_temporary_files(tmp_path):
    """Атомарная запись не оставляет временных файлов в корне."""
    storage = LandingStorage(tmp_path)

    storage.save_draft("<p>x</p>")

    assert sorted(path.name for path in tmp_path.iterdir()) == ["draft.html"]


# --------------------------------------------------------------------------
# Публикация
# --------------------------------------------------------------------------

def test_publish_copies_draft_to_index(tmp_path):
    """Публикация кладёт черновик в `index.html`, черновик остаётся."""
    storage = LandingStorage(tmp_path)
    storage.save_draft("<h1>Лендинг</h1>")

    assert storage.publish() is True

    assert storage.has_published() is True
    assert storage.index_path.read_text(encoding="utf-8") == "<h1>Лендинг</h1>"
    # Черновик не удаляется: редактор продолжает работу после публикации.
    assert storage.read_draft_html() == "<h1>Лендинг</h1>"


def test_publish_without_draft_is_noop(tmp_path):
    """Публиковать нечего — `False`, страница не появляется."""
    storage = LandingStorage(tmp_path)

    assert storage.publish() is False
    assert storage.has_published() is False


def test_publish_moves_previous_publication_to_prev(tmp_path):
    """Перед публикацией текущий `index.html` уходит в `index.prev.html`."""
    storage = LandingStorage(tmp_path)

    storage.save_draft("первая версия")
    storage.publish()
    storage.save_draft("вторая версия")
    storage.publish()

    assert storage.index_path.read_text(encoding="utf-8") == "вторая версия"
    assert storage.prev_path.read_text(encoding="utf-8") == "первая версия"


def test_publish_overwrites_prev_with_previous_publication(tmp_path):
    """Бэкап один: третья публикация перезаписывает `index.prev.html`."""
    storage = LandingStorage(tmp_path)

    for version in ("первая", "вторая", "третья"):
        storage.save_draft(version)
        storage.publish()

    assert storage.index_path.read_text(encoding="utf-8") == "третья"
    assert storage.prev_path.read_text(encoding="utf-8") == "вторая"


def test_first_publish_has_no_prev(tmp_path):
    """Первая публикация бэкап не создаёт: прошлой версии не было."""
    storage = LandingStorage(tmp_path)
    storage.save_draft("единственная")

    storage.publish()

    assert not storage.prev_path.exists()


def test_unpublish_removes_index_but_keeps_prev_and_draft(tmp_path):
    """Отмена публикации убирает `index.html`, бэкап и черновик остаются."""
    storage = LandingStorage(tmp_path)
    storage.save_draft("старая")
    storage.publish()
    storage.save_draft("новая")
    storage.publish()

    storage.unpublish()

    assert storage.has_published() is False
    assert not storage.index_path.exists()
    assert storage.prev_path.read_text(encoding="utf-8") == "старая"
    assert storage.read_draft_html() == "новая"


def test_unpublish_without_publication_is_noop(tmp_path):
    """Повторная отмена публикации — не ошибка."""
    storage = LandingStorage(tmp_path)

    storage.unpublish()

    assert storage.has_published() is False


# --------------------------------------------------------------------------
# Ассеты
# --------------------------------------------------------------------------

def test_save_asset_generates_uuid_name_and_returns_it(tmp_path):
    """Имя ассета — uuid и расширение; исходное имя в путь не попадает."""
    storage = LandingStorage(tmp_path)

    name = storage.save_asset("Моя картинка.PNG", b"\x89PNG")

    assert name.endswith(".png")
    assert "Моя" not in name
    assert is_asset_name(name)
    assert (tmp_path / "assets" / name).read_bytes() == b"\x89PNG"


def test_save_asset_does_not_overwrite_same_filename(tmp_path):
    """Две картинки с одинаковым именем получают разные имена на диске."""
    storage = LandingStorage(tmp_path)

    first = storage.save_asset("photo.png", b"one")
    second = storage.save_asset("photo.png", b"two")

    assert first != second
    assert (tmp_path / "assets" / first).read_bytes() == b"one"
    assert (tmp_path / "assets" / second).read_bytes() == b"two"


@pytest.mark.parametrize(
    "extension",
    sorted(ALLOWED_ASSET_EXTENSIONS),
)
def test_save_asset_accepts_allowed_extensions(tmp_path, extension):
    """Все расширения из allowlist сохраняются."""
    storage = LandingStorage(tmp_path)

    name = storage.save_asset(f"image.{extension.upper()}", b"x")

    assert name.endswith(f".{extension}")
    assert is_asset_name(name)


@pytest.mark.parametrize(
    "filename",
    ["virus.exe", "page.html", "noext", "", "script.js"],
    ids=["exe", "html", "no-ext", "empty", "js"],
)
def test_save_asset_rejects_non_image(tmp_path, filename):
    """Загрузка принимает только картинки: остальное — `ValueError`."""
    storage = LandingStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.save_asset(filename, b"x")


def test_list_assets_returns_saved_names(tmp_path):
    """Список ассетов — только файлы каталога, отсортированные по имени."""
    storage = LandingStorage(tmp_path)
    first = storage.save_asset("a.png", b"a")
    second = storage.save_asset("b.jpg", b"b")

    assert storage.list_assets() == sorted([first, second])


def test_list_assets_ignores_directories(tmp_path):
    """Подкаталог в `assets/` не считается ассетом."""
    storage = LandingStorage(tmp_path)
    (tmp_path / "assets" / "nested").mkdir(parents=True)

    assert storage.list_assets() == []


def test_remove_asset_deletes_file_and_tolerates_missing(tmp_path):
    """Удаление ассета; повторное удаление — не ошибка."""
    storage = LandingStorage(tmp_path)
    name = storage.save_asset("a.png", b"a")

    storage.remove_asset(name)
    storage.remove_asset(name)

    assert storage.list_assets() == []


@pytest.mark.parametrize(
    "name",
    ["../secret.png", "assets/../secret.png", "..", ".", "", "a/b.png"],
    ids=["parent", "nested-parent", "dots", "dot", "empty", "slash"],
)
def test_asset_path_rejects_traversal(tmp_path, name):
    """Имя с разделителями или точками не превращается в путь на диске."""
    storage = LandingStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.asset_path(name)


@pytest.mark.parametrize(
    "name",
    [
        "not-a-uuid.png",
        "0123456789abcdef0123456789abcdef.png",
        "01234567-89ab-cdef-0123-456789abcdef.exe",
        "01234567-89ab-cdef-0123-456789abcdef.png.exe",
        "../01234567-89ab-cdef-0123-456789abcdef.png",
    ],
    ids=["not-uuid", "no-dashes", "bad-ext", "double-ext", "traversal"],
)
def test_is_asset_name_rejects_foreign_names(name):
    """Публичный маршрут принимает только сгенерированные имена."""
    assert is_asset_name(name) is False


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("a.png", b"\x89PNG\r\n\x1a\nrest"),
        ("a.jpg", b"\xff\xd8\xff\xe0rest"),
        ("a.jpeg", b"\xff\xd8\xff\xe0rest"),
        ("a.gif", b"GIF87arest"),
        ("a.gif", b"GIF89arest"),
        ("a.webp", b"RIFF\x10\x00\x00\x00WEBPrest"),
        ("a.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
    ],
    ids=["png", "jpg", "jpeg", "gif87", "gif89", "webp", "svg"],
)
def test_is_valid_asset_content_accepts_matching_files(filename, content):
    """Содержимое совпадает с расширением — файл принимается."""
    assert is_valid_asset_content(filename, content) is True


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("a.png", b"plain text"),
        ("a.jpg", b"\x89PNG\r\n\x1a\n"),
        ("a.gif", b"RIFF\x10\x00\x00\x00WEBP"),
        ("a.webp", b"RIFF\x10\x00\x00\x00XXXX"),
        ("a.webp", b"RIFFWEBP"),
        ("a.svg", b""),
        ("a.png", b""),
        ("a.exe", b"\x89PNG\r\n\x1a\n"),
    ],
    ids=[
        "png-text",
        "jpg-png",
        "gif-webp",
        "webp-bad-marker",
        "webp-short",
        "svg-empty",
        "png-empty",
        "unknown-ext",
    ],
)
def test_is_valid_asset_content_rejects_foreign_files(filename, content):
    """Несовпадение сигнатуры, пустое тело и чужое расширение — отказ."""
    assert is_valid_asset_content(filename, content) is False


# --------------------------------------------------------------------------
# Конфигурация
# --------------------------------------------------------------------------

def test_settings_default_landing_root():
    """По умолчанию лендинг лежит в `./landing`."""
    assert Settings(_env_file=None).landing_root == "./landing"


def test_env_overrides_landing_root(monkeypatch):
    """`LANDING_ROOT` из окружения переопределяет каталог."""
    monkeypatch.setenv("LANDING_ROOT", "/data/landing")
    assert Settings(_env_file=None).landing_root == "/data/landing"
