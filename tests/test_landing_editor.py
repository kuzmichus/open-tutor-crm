"""Тесты редактора лендинга: доступ, загрузка, сохранение и вендоринг.

Редактор — автономная страница GrapesJS: из `draft.html` в неё попадают
только тело (без скриптов) и первый `<style>`, а сохранение снова собирает
полный документ, сохраняет `<title>` и идемпотентно гарантирует тег
`/static/landing-auth.js`.

Публичная отдача и страница управления живут в соседних файлах
(`test_landing_public.py`, `test_landing_page.py`).
"""

import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import settings
from app.landing.services.draft_render import (
    AUTH_SCRIPT,
    build_document,
    default_title,
    ensure_auth_script,
    extract_body,
    extract_first_style,
    extract_title,
    render_draft_document,
    strip_scripts,
)
from app.landing.services.storage import LandingStorage

PASSWORD = "Секретный-Пароль-1"
EMAIL = "landing-editor@example.com"

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
        about="Готовлю к экзаменам и объясняю сложное простыми словами.",
        experience="8 лет",
        hourly_rate=Decimal("1200"),
        phone="+7 (999) 123-45-67",
    )
    _login(client)
    return tutor_id


def _draft_payload(response):
    """Достаёт JSON черновика из `<script id="landing-draft">`."""
    match = re.search(
        r'<script type="application/json" id="landing-draft">(.*?)</script>',
        response.text,
        re.DOTALL,
    )
    assert match is not None, "JSON черновика не найден в странице редактора"
    return json.loads(match.group(1))


# --------------------------------------------------------------------------
# Доступ
# --------------------------------------------------------------------------


def test_editor_requires_login(client, landing_root, single_mode):
    """Без сессии редактор ведёт на вход."""
    response = client.get("/tutor/landing/editor", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert not (landing_root / "draft.html").exists()


def test_editor_is_not_found_in_multi_mode(client, tutor_factory, landing_root):
    """В мульти-режиме редактор и сохранение отвечают 404."""
    tutor_factory(email=EMAIL, password=PASSWORD)
    _login(client)

    assert client.get("/tutor/landing/editor").status_code == 404
    response = client.post(
        "/tutor/landing/draft",
        json={"html": "<div>Новый</div>", "css": ".x{color:red}"},
    )
    assert response.status_code == 404
    assert not (landing_root / "draft.html").exists()


# --------------------------------------------------------------------------
# Загрузка черновика
# --------------------------------------------------------------------------


def test_editor_creates_missing_draft(client, owner, landing_root):
    """Черновика нет — редактор создаёт его из шаблона профиля."""
    response = client.get("/tutor/landing/editor")

    assert response.status_code == 200
    draft = (landing_root / "draft.html").read_text(encoding="utf-8")
    assert "Анна Иванова" in draft
    assert "hero__name" in draft
    assert response.headers["cache-control"] == "no-store"


def test_editor_page_is_standalone(client, owner):
    """Редактор — автономный документ с локальным GrapesJS и русским UI."""
    page = client.get("/tutor/landing/editor").text

    assert "<!doctype html>" in page
    assert 'id="gjs"' in page
    assert "/static/dist/grapesjs/grapes.min.css" in page
    assert "/static/dist/grapesjs/grapes.min.js" in page
    assert "/static/dist/grapesjs/i18n-ru.js" in page
    assert "Сохранить" in page
    assert "Предпросмотр" in page
    assert "Назад к управлению" in page
    assert "locale: 'ru'" in page
    assert "localeFallback: 'en'" in page
    assert "storageManager" in page
    assert "type: 'none'" in page

    assert "/static/styles.css" not in page
    assert 'class="sidebar' not in page
    assert "unpkg.com" not in page
    assert "cdn." not in page
    # Скрипт подмены входов не подключается в канвасе: репетитор видит
    # исходные кнопки «Вход…».
    assert "/static/landing-auth.js" not in page


def test_editor_payload_extracts_body_and_first_style(client, owner):
    """В редактор попадают тело без скриптов и только первый `<style>`."""
    payload = _draft_payload(client.get("/tutor/landing/editor"))

    assert "hero" in payload["body"]
    assert 'data-auth="student"' in payload["body"]
    assert "--accent" in payload["css"]
    assert "@media (max-width: 640px)" in payload["css"]
    assert "<script" not in payload["body"]
    assert "landing-auth.js" not in payload["body"]


# --------------------------------------------------------------------------
# Сохранение
# --------------------------------------------------------------------------


def test_save_writes_full_document(client, owner, landing_root):
    """Сохранение меняет `draft.html`, добавляя шапку и тег скрипта."""
    response = client.post(
        "/tutor/landing/draft",
        json={"html": '<div class="x">Новый</div>', "css": ".x{color:red}"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Сохранено"
    assert response.headers["cache-control"] == "no-store"

    draft = (landing_root / "draft.html").read_text(encoding="utf-8")
    assert '<div class="x">Новый</div>' in draft
    assert "<style>.x{color:red}</style>" in draft
    assert '<meta charset="utf-8">' in draft
    assert 'name="viewport"' in draft
    assert draft.count("landing-auth.js") == 1


def test_save_keeps_existing_title(client, owner, landing_root):
    """`<title>` текущего черновика переживает сохранение тела."""
    storage = LandingStorage(landing_root)
    storage.save_draft(
        "<!doctype html><html><head><title>Свой заголовок</title></head>"
        "<body><p>Старое</p></body></html>"
    )

    client.post(
        "/tutor/landing/draft",
        json={"html": "<p>Новое</p>", "css": ""},
    )

    draft = storage.read_draft_html()
    assert "<title>Свой заголовок</title>" in draft
    assert "<p>Новое</p>" in draft
    assert "Старое" not in draft


def test_save_without_draft_uses_default_title(client, owner, landing_root):
    """Без черновика заголовок строится из имени репетитора."""
    client.post(
        "/tutor/landing/draft",
        json={"html": "<p>Новое</p>", "css": ""},
    )

    draft = (landing_root / "draft.html").read_text(encoding="utf-8")
    assert "<title>Анна Иванова — репетитор</title>" in draft


def test_save_is_idempotent_for_auth_script(client, owner, landing_root):
    """Два сохранения и тег в HTML не создают второй `landing-auth.js`."""
    client.post("/tutor/landing/draft", json={"html": "<p>Раз</p>", "css": ""})
    client.post("/tutor/landing/draft", json={"html": "<p>Два</p>", "css": ""})
    client.post(
        "/tutor/landing/draft",
        json={
            "html": f"<p>Три</p>{AUTH_SCRIPT}",
            "css": "",
        },
    )

    draft = (landing_root / "draft.html").read_text(encoding="utf-8")
    assert draft.count("landing-auth.js") == 1


def test_invalid_payload_is_validation_error(client, owner):
    """Неверный JSON — 422 от FastAPI, а не 500."""
    response = client.post(
        "/tutor/landing/draft",
        json={"html": 123, "css": []},
    )
    assert response.status_code == 422


def test_round_trip_keeps_page_intact(client, owner, landing_root):
    """Открыл → ничего не менял → сохранил: страница не теряет содержимое."""
    client.post("/tutor/landing/reset")
    storage = LandingStorage(landing_root)
    before = storage.read_draft_html()

    payload = _draft_payload(client.get("/tutor/landing/editor"))
    response = client.post(
        "/tutor/landing/draft",
        json={"html": payload["body"], "css": payload["css"]},
    )
    assert response.status_code == 200

    after = storage.read_draft_html()
    assert "<title>Анна Иванова — репетитор по математике</title>" in after
    assert 'data-auth="student"' in after
    assert 'data-auth="parent"' in after
    assert 'data-auth="tutor"' in after
    assert "hero" in after
    assert "section" in after
    assert "--accent" in after
    assert "@media (max-width: 640px)" in after
    assert after.count("landing-auth.js") == 1
    assert before is not None


def test_manage_page_links_to_editor(client, owner):
    """Кнопка «Редактировать» на странице управления ведёт в редактор."""
    page = client.get("/tutor/landing").text

    assert 'href="/tutor/landing/editor"' in page
    assert "Редактировать" in page


# --------------------------------------------------------------------------
# Вендоринг
# --------------------------------------------------------------------------


def test_grapesjs_is_vendored_locally():
    """GrapesJS и русская локаль лежат локально и не пустые."""
    for name in ("grapes.min.js", "grapes.min.css", "i18n-ru.js", "LICENSE"):
        path = VENDOR_DIR / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name

    locale = (VENDOR_DIR / "i18n-ru.js").read_text(encoding="utf-8")
    assert "window.grapesjsI18nRu" in locale
    for section in (
        "assetManager",
        "blockManager",
        "deviceManager",
        "panels",
        "selectorManager",
        "styleManager",
        "traitManager",
        "domComponents",
    ):
        assert section in locale, section
    assert re.search(r"[А-Яа-яЁё]", locale)


# --------------------------------------------------------------------------
# Unit-тесты сборки и разбора документа
# --------------------------------------------------------------------------


def test_extract_body_handles_attributes_and_missing_body():
    assert extract_body('<html><body class="page">тело</body></html>') == "тело"
    assert extract_body("<html><head></head></html>") == ""


def test_extract_first_style_returns_only_first_block():
    document = "<style>.a{color:red}</style><style>.b{color:blue}</style>"
    assert extract_first_style(document) == ".a{color:red}"
    assert extract_first_style("<html></html>") == ""


def test_extract_title_strips_and_ignores_empty():
    assert extract_title("<title>  Заголовок  </title>") == "Заголовок"
    assert extract_title("<title>   </title>") is None
    assert extract_title("<html></html>") is None


def test_strip_scripts_removes_inline_and_external_tags():
    fragment = (
        '<p>До</p><script>alert(1)</script>'
        '<script src="/static/landing-auth.js" defer></script>'
        '<script src="x.js" />'
        "<p>После</p>"
    )
    result = strip_scripts(fragment)

    assert "<script" not in result
    assert "alert(1)" not in result
    assert "landing-auth.js" not in result
    assert "<p>До</p>" in result
    assert "<p>После</p>" in result


def test_ensure_auth_script_inserts_before_body_end():
    document = "<html><body><p>Текст</p></body></html>"
    result = ensure_auth_script(document)

    assert result == f"<html><body><p>Текст</p>{AUTH_SCRIPT}</body></html>"
    assert result.count("landing-auth.js") == 1


def test_ensure_auth_script_appends_without_body_end():
    result = ensure_auth_script("<p>Фрагмент</p>")
    assert result == f"<p>Фрагмент</p>{AUTH_SCRIPT}"


def test_ensure_auth_script_does_not_duplicate():
    document = f"<html><body>{AUTH_SCRIPT}</body></html>"
    assert ensure_auth_script(document) == document


def test_build_document_has_required_head_and_body():
    document = build_document(body="<p>Тело</p>", css=".x{color:red}", title="Заголовок")

    assert document.startswith("<!doctype html>")
    assert '<html lang="ru">' in document
    assert '<meta charset="utf-8">' in document
    assert 'name="viewport"' in document
    assert "<title>Заголовок</title>" in document
    assert "<style>.x{color:red}</style>" in document
    assert "<body><p>Тело</p></body>" in document


def test_default_title_escapes_name():
    tutor = SimpleNamespace(name="Иван <Иванов> & Ко")
    title = default_title(tutor)

    assert title == "Иван &lt;Иванов&gt; &amp; Ко — репетитор"
    assert "<" not in title


def test_render_draft_document_uses_existing_title():
    tutor = SimpleNamespace(name="Анна")
    existing = "<html><head><title>Свой</title></head><body></body></html>"
    document = render_draft_document(
        tutor, html="<p>Тело</p>", css="", existing_html=existing
    )

    assert "<title>Свой</title>" in document
    assert document.count("landing-auth.js") == 1


def test_render_draft_document_unwraps_editor_body():
    """`editor.getHtml()` отдаёт `<body>…</body>`: вторая обёртка не нужна."""
    tutor = SimpleNamespace(name="Анна")
    document = render_draft_document(
        tutor,
        html='<body><div class="hero">Тело</div></body>',
        css="",
        existing_html=None,
    )

    assert "<body><div class=\"hero\">Тело</div>" in document
    assert document.count("<body>") == 1
    assert document.count("</body>") == 1


def test_render_draft_document_falls_back_to_default_title():
    tutor = SimpleNamespace(name="Анна")
    document = render_draft_document(
        tutor, html="<p>Тело</p>", css="", existing_html=None
    )

    assert "<title>Анна — репетитор</title>" in document
