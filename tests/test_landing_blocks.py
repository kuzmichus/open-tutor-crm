"""Тесты набора блоков редактора лендинга.

Проверяется, что панель «Блоки» GrapesJS наполняется готовыми секциями
лендинга в дизайне CRM и простыми элементами, что подписи блоков есть в
русской локали и что блок «Изображение» открывает Asset Manager сразу
после вставки.

Доступ и сохранение редактора живут в `test_landing_editor.py`, загрузка
картинок — в `test_landing_assets.py`.
"""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.config import settings
from app.landing.services.blocks import (
    BLOCK_CATEGORIES,
    CATEGORY_BASIC,
    CATEGORY_LANDING,
    CATEGORY_LAYOUT,
    landing_blocks,
)

PASSWORD = "Секретный-Пароль-1"
EMAIL = "landing-blocks@example.com"

VENDOR_DIR = Path(__file__).resolve().parents[1] / "app" / "static" / "dist" / "grapesjs"


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


def _blocks_payload(response):
    """Достаёт JSON блоков из `<script id="landing-blocks">`."""
    match = re.search(
        r'<script type="application/json" id="landing-blocks">(.*?)</script>',
        response.text,
        re.DOTALL,
    )
    assert match is not None, "JSON блоков не найден в странице редактора"
    return json.loads(match.group(1))


# --------------------------------------------------------------------------
# Набор блоков как данные
# --------------------------------------------------------------------------


def test_landing_blocks_cover_main_sections():
    """В наборе есть все основные секции лендинга и служебные блоки."""
    blocks = landing_blocks("/s/tutor-id")
    ids = [block["id"] for block in blocks]

    for block_id in (
        "header",
        "hero",
        "about",
        "price",
        "contacts",
        "footer",
    ):
        assert block_id in ids, f"нет секции {block_id}"
    for block_id in ("heading", "text", "image", "button", "divider"):
        assert block_id in ids, f"нет базового блока {block_id}"
    for block_id in ("column2", "column3"):
        assert block_id in ids, f"нет блока раскладки {block_id}"


def test_blocks_use_only_known_categories():
    """Каждый блок отнесён к одной из объявленных категорий."""
    for block in landing_blocks("/s/tutor-id"):
        assert block["category"] in BLOCK_CATEGORIES, block["id"]


def test_blocks_are_grouped_into_categories():
    """Секции лендинга, простые элементы и раскладка лежат в своих группах."""
    by_id = {block["id"]: block for block in landing_blocks("/s/tutor-id")}

    assert by_id["hero"]["category"] == CATEGORY_LANDING
    assert by_id["text"]["category"] == CATEGORY_BASIC
    assert by_id["column2"]["category"] == CATEGORY_LAYOUT


def test_cta_links_to_tutor_public_page():
    """CTA «Обложка» и кнопка ведут на публичную страницу этого репетитора."""
    blocks = {block["id"]: block for block in landing_blocks("/s/tutor-id")}

    assert 'href="/s/tutor-id"' in blocks["hero"]["content"]
    assert "Записаться на занятие" in blocks["hero"]["content"]
    assert 'href="/s/tutor-id"' in blocks["button"]["content"]


def test_image_block_has_no_empty_src_and_opens_asset_manager():
    """Блок изображения не тащит `src=""` и помечен для выбора картинки."""
    image = {block["id"]: block for block in landing_blocks("/s/tutor-id")}["image"]

    assert 'src=""' not in image["content"]
    assert "data-landing-image" in image["content"]
    assert image["content"].startswith("<img")


def test_blocks_markup_has_no_source_indentation():
    """HTML блоков не начинается с отступов: GrapesJS парсит строку как есть."""
    for block in landing_blocks("/s/tutor-id"):
        assert block["content"] == block["content"].strip(), block["id"]
        assert not block["content"].startswith("\n"), block["id"]


# --------------------------------------------------------------------------
# Панель блоков в редакторе
# --------------------------------------------------------------------------


def test_editor_embeds_blocks_and_enables_click_insert(client, owner):
    """Редактор получает JSON блоков и включает вставку блока по клику."""
    response = client.get("/tutor/landing/editor")
    page = response.text

    assert 'id="landing-blocks"' in page
    assert "blockManager" in page
    assert "appendOnClick: true" in page
    # Блоки приходят из сервиса, а не зашиты в шаблон.
    assert "var blocks = JSON.parse(" in page

    blocks = _blocks_payload(response)
    assert [block["id"] for block in blocks][:3] == ["header", "hero", "about"]


def test_editor_blocks_use_tutor_cta_url(client, owner):
    """CTA в блоках ведёт на публичную страницу владельца, а не на заглушку."""
    blocks = _blocks_payload(client.get("/tutor/landing/editor"))
    by_id = {block["id"]: block for block in blocks}

    assert f'href="/s/{owner}"' in by_id["hero"]["content"]


def test_editor_opens_asset_manager_for_inserted_image(client, owner):
    """В JS редактора есть обработчик вставки блока изображения."""
    page = client.get("/tutor/landing/editor").text

    assert "function pickImage(component)" in page
    assert "component:add" in page
    assert "data-landing-image" in page
    assert "types: ['image']" in page


# --------------------------------------------------------------------------
# Подписи в русской локали
# --------------------------------------------------------------------------


def test_locale_has_labels_for_every_block():
    """У каждого блока и категории есть русская подпись в локали."""
    locale = (VENDOR_DIR / "i18n-ru.js").read_text(encoding="utf-8")
    labels = _locale_section(locale, "labels")
    categories = _locale_section(locale, "categories")

    for block in landing_blocks("/s/tutor-id"):
        assert block["id"] in labels, f"нет подписи блока {block['id']}"
    for category in BLOCK_CATEGORIES:
        assert category in categories, f"нет подписи категории {category}"


def _locale_section(locale: str, name: str) -> dict[str, str]:
    """Плоская секция `blockManager.<name>` из файла локали.

    Файл — обычный скрипт, а не JSON (в нём комментарии), поэтому секция
    вырезается регуляркой и разбирается как пары `ключ: 'значение'`.
    """
    match = re.search(
        rf"{name}:\s*\{{(.*?)\}}",
        locale,
        re.DOTALL,
    )
    assert match is not None, name
    pairs = re.findall(r"['\"]?([\w-]+)['\"]?\s*:\s*'([^']*)'", match.group(1))
    return dict(pairs)
