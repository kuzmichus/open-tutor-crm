"""Набор favicon: файлы на диске, манифест, разметка head и маршруты отдачи.

Favicon — единственный ассет, который браузер запрашивает сам, без нашей
разметки: `/favicon.ico` из корня сайта, иконки из манифеста при установке
PWA. Ошибка здесь не видна на странице — вкладка просто остаётся с
стандартной «пустой» иконкой, а ломается это тихо (не тот размер, битый
ICO, манифест со ссылкой на несуществующий файл). Поэтому набор проверяется
структурно, без Pillow: читаем сигнатуры и заголовки сами.

Свежесть файлов (что их собрал именно текущий исходник) тестами не
проверяется — пересборка требует Pillow, а он не зависимость проекта.
Команда пересборки: `uv run --with pillow python scripts/build_favicons.py`.
"""

import json
import re
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FAVICONS = ROOT / "app" / "static" / "favicons"

PASSWORD = "Секретный-Пароль-1"

# Размеры, которые обязаны быть в наборе: вкладка и закладки (16/32),
# ярлык на рабочем столе (48 — внутри ICO), iOS (180), PWA (192/512).
PNG_SIZES = {
    "favicon-16x16.png": (16, 16),
    "favicon-32x32.png": (32, 32),
    "apple-touch-icon.png": (180, 180),
    "android-chrome-192x192.png": (192, 192),
    "android-chrome-512x512.png": (512, 512),
    "android-chrome-maskable-512x512.png": (512, 512),
}

ICO_SIZES = {(16, 16), (32, 32), (48, 48)}

# Ссылки, которые обязаны стоять в head каждой страницы. Проверяем
# `rel` и путь, а не точную строку: порядок атрибутов — дело шаблона.
EXPECTED_LINKS = [
    ("icon", "/static/favicons/favicon.ico"),
    ("icon", "/static/favicons/favicon.svg"),
    ("icon", "/static/favicons/favicon-32x32.png"),
    ("icon", "/static/favicons/favicon-16x16.png"),
    ("apple-touch-icon", "/static/favicons/apple-touch-icon.png"),
    ("mask-icon", "/static/favicons/safari-pinned-tab.svg"),
    ("manifest", "/static/favicons/site.webmanifest"),
]


def _png_size(path: Path) -> tuple[int, int]:
    """Размер PNG из IHDR: сигнатура, длина, тип, ширина, высота.

    Читаем вручную, а не через Pillow: тест должен работать в том же
    окружении, что и остальные тесты проекта, без лишней зависимости.
    """
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name}: не PNG"
    length, kind = struct.unpack(">I4s", data[8:16])
    assert length == 13 and kind == b"IHDR", f"{path.name}: первый чанк не IHDR"
    return struct.unpack(">II", data[16:24])


def _ico_sizes(path: Path) -> set[tuple[int, int]]:
    """Размеры записей ICO из ICONDIR/ICONDIRENTRY.

    Ширина и высота в записи — один байт, 0 означает 256: формат писался
    под 16-битные числа и больший размер в байт не влезает.
    """
    data = path.read_bytes()
    reserved, icon_type, count = struct.unpack("<HHH", data[:6])
    assert (reserved, icon_type) == (0, 1), f"{path.name}: не ICONDIR"
    sizes: set[tuple[int, int]] = set()
    for index in range(count):
        offset = 6 + index * 16
        width, height = data[offset], data[offset + 1]
        sizes.add((width or 256, height or 256))
    return sizes


# --------------------------------------------------------------------------
# 8.1–8.2 Файлы набора
# --------------------------------------------------------------------------

def test_every_favicon_file_exists_and_is_not_empty():
    """Все файлы набора на месте: пропавший файл — битая иконка без ошибки."""
    for name in [*PNG_SIZES, "favicon.ico", "favicon.svg", "safari-pinned-tab.svg",
                 "site.webmanifest"]:
        path = FAVICONS / name
        assert path.is_file(), f"нет файла набора: {path}"
        assert path.stat().st_size > 0, f"пустой файл набора: {path}"


@pytest.mark.parametrize(("name", "size"), sorted(PNG_SIZES.items()))
def test_png_icons_have_expected_size(name: str, size: tuple[int, int]):
    """PNG-иконки объявлены в разметке и манифесте с точным размером.

    Браузер верит `sizes="32x32"` и масштабирует файл под него: неверный
    размер даёт мыльную иконку вместо резкой.
    """
    assert _png_size(FAVICONS / name) == size


def test_favicon_ico_contains_tab_and_desktop_sizes():
    """Мультиразмерный ICO: 16 — вкладка, 32 — закладки, 48 — рабочий стол."""
    assert _ico_sizes(FAVICONS / "favicon.ico") == ICO_SIZES


def test_vector_icons_are_svg():
    """SVG-файлы начинаются с корневого `<svg>` и объявляют viewBox.

    `mask-icon` без `viewBox` Safari масштабирует по-своему, а `favicon.svg`
    без него теряет пропорции при отрисовке в нестандартном размере.
    """
    for name in ("favicon.svg", "safari-pinned-tab.svg"):
        markup = (FAVICONS / name).read_text(encoding="utf-8")
        assert markup.lstrip().startswith("<svg"), f"{name}: нет корневого <svg>"
        assert 'viewBox="0 0 200 200"' in markup, f"{name}: нет viewBox"
        # Внешних ссылок быть не должно: иконка не ходит в сеть (AGENTS.md п. 8).
        assert "http://" not in markup.replace('xmlns="http://www.w3.org/2000/svg"', "")


# --------------------------------------------------------------------------
# 8.3 Манифест
# --------------------------------------------------------------------------

def test_manifest_is_valid_and_points_to_existing_files():
    """Манифест — валидный JSON, и каждая иконка из него существует на диске.

    Битая ссылка в манифесте не ломает страницу: браузер молча отказывает
    в установке PWA, и заметить это можно только по консоли.
    """
    manifest = json.loads((FAVICONS / "site.webmanifest").read_text(encoding="utf-8"))
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["name"] and manifest["short_name"]
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", manifest["theme_color"])
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", manifest["background_color"])

    icons = manifest["icons"]
    assert {(icon["sizes"], icon["purpose"]) for icon in icons} >= {
        ("192x192", "any"),
        ("512x512", "any"),
        ("512x512", "maskable"),
    }
    for icon in icons:
        assert icon["type"] == "image/png"
        assert icon["src"].startswith("/static/favicons/")
        path = ROOT / "app" / icon["src"].lstrip("/")
        assert path.is_file(), f"манифест ссылается на отсутствующий файл: {icon['src']}"
        assert _png_size(path) == tuple(int(part) for part in icon["sizes"].split("x"))


# --------------------------------------------------------------------------
# 8.4 Разметка head на всех поверхностях
# --------------------------------------------------------------------------

def _assert_favicon_head(markup: str, where: str) -> None:
    """В head есть все ссылки набора и нет ссылок на внешние хосты."""
    head = markup[: markup.index("</head>")]
    # Теги разбираем, а не ищем подстроку: у SVG-иконки между `rel` и
    # `href` стоит `type`, и проверка на точную строку падала бы на
    # порядке атрибутов, а не на отсутствии ссылки.
    links = {
        (rel, href)
        for tag in re.findall(r"<link\b[^>]*>", head)
        for rel in re.findall(r'rel="([^"]+)"', tag)
        for href in re.findall(r'href="([^"]+)"', tag)
    }
    for rel, href in EXPECTED_LINKS:
        assert (rel, href) in links, f"{where}: в head нет {rel} → {href}"
    # `theme-color` в head обязан совпадать с манифестом: браузер для темы
    # вкладки берёт мету, а для установленного PWA — манифест. Рассогласование
    # даёт «мигание» цвета при установке приложения.
    theme = json.loads((FAVICONS / "site.webmanifest").read_text(encoding="utf-8"))["theme_color"]
    assert f'<meta name="theme-color" content="{theme}">' in head, where
    # Набор локальный: любая абсолютная ссылка в head — регрессия «без CDN».
    external = re.findall(r'(?:href|src)="https?://[^"]+"', head)
    assert not external, f"{where}: внешние ссылки в head: {external}"


def test_head_links_on_auth_page(client):
    """Страница входа — самая первая поверхность, которую видит человек."""
    response = client.get("/tutor/login")
    assert response.status_code == 200
    _assert_favicon_head(response.text, "/tutor/login")


def test_head_links_on_404_page(client):
    """404 наследует тот же макет: иконка не должна пропадать на ошибке."""
    response = client.get("/net-takoy-stranitsy")
    assert response.status_code == 404
    _assert_favicon_head(response.text, "404")


def test_head_links_on_tutor_cabinet(client, tutor_factory):
    """Страница кабинета после входа — основная рабочая поверхность."""
    tutor_factory(email="favicon@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "favicon@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    response = client.get("/tutor/")
    assert response.status_code == 200
    _assert_favicon_head(response.text, "/tutor/")


def test_head_links_on_public_booking_page(client, tutor_factory):
    """Публичная страница записи — единственная, которую видит не клиент CRM."""
    tutor_id = tutor_factory()
    response = client.get(f"/s/{tutor_id}")
    assert response.status_code == 200
    _assert_favicon_head(response.text, f"/s/{tutor_id}")


# --------------------------------------------------------------------------
# 8.5–8.6 Отдача файлов
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("url", "content_type"),
    [
        ("/static/favicons/favicon.ico", "image/vnd.microsoft.icon"),
        ("/static/favicons/favicon.svg", "image/svg+xml"),
        ("/static/favicons/apple-touch-icon.png", "image/png"),
        ("/static/favicons/site.webmanifest", "application/manifest+json"),
    ],
)
def test_favicon_files_are_served_with_revalidation(client, url: str, content_type: str):
    """Файлы набора отдаются с правильным типом и политикой `no-cache`.

    Неверный `Content-Type` у манифеста — отказ в установке PWA; `no-cache`
    нужен, чтобы обновление знака подхватывалось без сброса кэша браузера.
    """
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == content_type
    assert response.headers["cache-control"] == "no-cache"


def test_root_favicon_returns_the_same_bytes(client):
    """`GET /favicon.ico` отдаёт ту же иконку, что лежит в наборе.

    По этому адресу иконку запрашивают браузеры и внешние сервисы, не читая
    разметку. Без маршрута они получали HTML страницы 404.
    """
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/vnd.microsoft.icon"
    assert response.headers["cache-control"] == "no-cache"
    assert response.content == (FAVICONS / "favicon.ico").read_bytes()
