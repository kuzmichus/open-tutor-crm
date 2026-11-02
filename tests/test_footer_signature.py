"""Тесты подписи сервиса в подвале: версия и ссылка на исходники.

Задача «подпись в подвале»: репетитор, сообщающий о проблеме, и владелец
сервера, проверяющий обновление, видят работающую версию без консоли, а
рядом — ссылку на репозиторий проекта.

Версия в разметке не литерал: она приходит из `pyproject.toml` через
`app.__repository_url__`/`__version__` (глобальные переменные Jinja
`app_version`/`app_repository_url`). Поэтому тест сверяет отрисованную
подпись именно с манифестом — литерал в шаблоне он бы не поймал.
"""

import re
import tomllib
from pathlib import Path

import pytest

from app import __repository_url__, __version__

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
PASSWORD = "Секретный-Пароль-1"
GITHUB_URL = "https://github.com/kuzmichus/open-tutor-crm/"


def _manifest_version() -> str:
    with PYPROJECT.open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)["project"]["version"]


def _login_tutor(client, email: str = "signature-tutor@example.com") -> None:
    client.post(
        "/tutor/register",
        data={
            "name": "Подписной",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )


def _sidebar(page: str) -> str:
    start = page.index('<aside class="sidebar"')
    return page[start : page.index("</aside>", start)]


# --------------------------------------------------------------------------
# Источник данных подписи
# --------------------------------------------------------------------------

def test_version_and_repository_come_from_manifest_and_code():
    """Версия подписи — из манифеста, адрес репозитория — из `app`."""
    assert __version__ == _manifest_version()
    assert __repository_url__ == GITHUB_URL


def test_templates_have_no_hardcoded_version():
    """В шаблонах нет литерала версии: только переменная окружения.

    Литерал `v0.2.0` в разметке — второй источник истины: после bump'а
    подпись показывала бы старую версию, хотя `app.version` новая.
    """
    for path in (ROOT / "app").rglob("*.html"):
        markup = path.read_text(encoding="utf-8")
        assert not re.search(r"\bv\d+\.\d+\.\d+\b", markup), path


# --------------------------------------------------------------------------
# Кабинет репетитора
# --------------------------------------------------------------------------

def test_tutor_sidebar_footer_shows_current_version(client):
    """В подвале сайдбара репетитора — актуальная версия."""
    _login_tutor(client)
    sidebar_html = _sidebar(client.get("/tutor/").text)

    assert "app-signature" in sidebar_html
    assert f"v{_manifest_version()}" in sidebar_html
    # Подпись — в футере, ниже строки пользователя, а не в основном меню.
    assert sidebar_html.index("app-signature") > sidebar_html.index("user-row-wrap")


def test_tutor_footer_links_to_github_with_mark(client):
    """Ссылка на GitHub — внешняя, безопасная и со значком-иконкой."""
    _login_tutor(client, email="signature-github@example.com")
    sidebar_html = _sidebar(client.get("/tutor/").text)

    link = re.search(r'<a class="app-signature__link"(.*?)>', sidebar_html, re.S)
    assert link, "в подписи нет ссылки на исходники"
    attrs = link.group(1)
    assert f'href="{GITHUB_URL}"' in attrs
    assert 'target="_blank"' in attrs
    # rel="noopener": чужая вкладка не получает доступ к window.opener.
    assert "noopener" in attrs
    assert "noreferrer" in attrs
    # Значок — inline SVG (в наборе Lucide нет брендовых иконок), причём
    # декоративный: имя ссылки даёт aria-label.
    assert 'class="app-signature__icon"' in sidebar_html
    assert 'aria-label="Исходный код Open Tutor CRM на GitHub"' in sidebar_html


def test_footer_signature_is_near_the_footer_end(client):
    """Подпись — самая нижняя часть сайдбара, после профиля и выхода."""
    _login_tutor(client, email="signature-position@example.com")
    sidebar_html = _sidebar(client.get("/tutor/").text)

    assert sidebar_html.index("/tutor/logout") < sidebar_html.index("app-signature")


# --------------------------------------------------------------------------
# Остальные поверхности
# --------------------------------------------------------------------------

def test_cabinet_sidebar_shows_signature(client, tutor_factory, student_factory):
    """Подвал кабинета ученика повторяет подпись CRM."""
    from app.cabinet.services.sessions import create_session
    from app.database import SessionLocal

    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    with SessionLocal() as db:
        token = create_session(db, student_id)
    client.cookies.set("student_session", token)

    sidebar_html = _sidebar(client.get("/student").text)
    assert f"v{_manifest_version()}" in sidebar_html
    assert GITHUB_URL in sidebar_html


@pytest.mark.parametrize(
    "url",
    ["/tutor/login", "/tutor/register", "/student/login", "/parent/login"],
)
def test_public_pages_show_signature(client, url):
    """Страницы до входа тоже показывают версию: по ней сообщают о проблеме."""
    response = client.get(url)
    assert response.status_code == 200, url
    assert f"v{_manifest_version()}" in response.text, url
    assert GITHUB_URL in response.text, url


def test_404_page_shows_signature(client):
    """На 404 версия видна: по ней понятно, не устарел ли образ."""
    response = client.get("/tutor/no-such-page")
    assert response.status_code == 404
    assert f"v{_manifest_version()}" in response.text
    assert GITHUB_URL in response.text


# --------------------------------------------------------------------------
# Разметка и стили
# --------------------------------------------------------------------------

def test_signature_markup_is_shared_partial():
    """Одна разметка подписи на все поверхности — партиал `_footer_signature.html`.

    Копия подписи в каждом шаблоне разошлась бы: версия или адрес правились
    бы в одном месте и оставались старыми в другом.
    """
    partial = ROOT / "app" / "templates" / "_footer_signature.html"
    assert partial.is_file()

    users = [
        path
        for path in (ROOT / "app").rglob("*.html")
        if '{% include "_footer_signature.html" %}' in path.read_text(encoding="utf-8")
    ]
    # Репетитор, кабинет ученика, кабинет родителя, вход/регистрация
    # (auth.html), вход кабинетов (cabinet/base.html), 404.
    assert len(users) >= 6, [path.name for path in users]


def test_signature_has_css_rules():
    """Классы подписи описаны в styles.css — иначе текст потеряет вид."""
    css = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    for selector in (
        ".app-signature",
        ".app-signature__version",
        ".app-signature__link",
        ".app-signature__icon",
    ):
        assert selector in css, f"нет правила {selector}"
