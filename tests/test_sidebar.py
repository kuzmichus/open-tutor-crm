"""Тесты разметки сайдбара: есть на /tutor/, нет на /."""

PASSWORD = "Секретный-Пароль-1"


def _login(client, email="sidebar-user@example.com", password=PASSWORD):
    client.post(
        "/tutor/register",
        data={
            "name": "Сайдбанный",
            "email": email,
            "password": password,
            "password_confirm": password,
        },
    )
    return client.post(
        "/tutor/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def test_index_has_no_sidebar(client):
    """Публичная главная (/) использует стили, но не содержит сайдбара."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'class="sidebar"' not in response.text
    assert "styles.css" in response.text


def test_tutor_home_has_sidebar_when_authorized(client):
    """Авторизованный /tutor/ отрисовывает сайдбар с активным пунктом."""
    _login(client)
    response = client.get("/tutor/")
    assert response.status_code == 200
    assert 'class="sidebar"' in response.text
    assert "nav-item--active" in response.text
    assert "Календарь" in response.text
    assert "Настройки" in response.text


def test_sidebar_links_are_namespaced_under_tutor(client):
    """Локальные пункты сайдбара ведут на маршруты `/tutor/*`."""
    _login(client, email="namespaced-user@example.com")
    page = client.get("/tutor/").text
    start = page.index('<aside class="sidebar"')
    sidebar_html = page[start : page.index("</aside>", start)]

    assert 'href="/tutor/calendar"' in sidebar_html  # Календарь
    assert 'href="/tutor/"' in sidebar_html  # Главная
    # Старых «голых» ссылок в неймспейсе не осталось.
    assert 'href="/calendar"' not in sidebar_html
    assert 'href="/"' not in sidebar_html


def test_sidebar_header_uses_brand_logo(client):
    """В шапке сайдбара — SVG-логотип (облако + шестерёнка), а не lucide-иконка."""
    _login(client, email="logo-user@example.com")
    response = client.get("/tutor/")
    assert response.status_code == 200
    assert 'class="brand-logo"' in response.text
    assert "brand-logo-gradient" in response.text
    assert 'data-lucide="graduation-cap"></i>\n        </span>' not in response.text


def test_public_pages_use_brand_logo(client):
    """Логотип на публичных страницах (/, /tutor/login) — тот же SVG."""
    for url in ("/", "/tutor/login"):
        response = client.get(url)
        assert response.status_code == 200, url
        assert 'class="brand-logo"' in response.text, url


def test_tutor_home_without_session_no_sidebar(client):
    """Неавторизованный /tutor/ редиректит на вход (сайдбара не отдаёт)."""
    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_login_page_has_no_sidebar(client):
    """Публичные /tutor/* (вход, регистрация) — без сайдбара."""
    for url in ("/tutor/login", "/tutor/register"):
        response = client.get(url)
        assert response.status_code == 200, url
        assert 'class="sidebar"' not in response.text, url


def test_sidebar_has_no_stray_braces(client):
    """В отрисованном сайдбаре нет «лишних» фигурных скобок.

    Незакрытая по правилам Jinja-комментария строка `{# ... #}}` оставляла
    лишний `}` прямо в разметке между пунктами меню.
    """
    _login(client, email="brace-user@example.com")
    page = client.get("/tutor/").text
    start = page.index('<aside class="sidebar"')
    sidebar_html = page[start : page.index("</aside>", start)]

    assert "#}" not in sidebar_html
    assert not [line for line in sidebar_html.splitlines() if line.strip() == "}"]


def test_sidebar_toggle_is_wired_for_collapsing(client):
    """Кнопка-«язычок» помечена data-sidebar-toggle и управляет навигацией."""
    _login(client, email="toggle-user@example.com")
    page = client.get("/tutor/").text
    assert "data-sidebar-toggle" in page
    assert 'aria-controls="sidebar-nav"' in page
    assert 'aria-expanded="true"' in page
    assert 'id="sidebar-nav"' in page
    # Старый атрибут без обработчика в app.js больше не используется.
    assert "data-sidebar-close" not in page


def test_sidebar_collapse_state_has_css_and_js(client):
    """Свёрнутое состояние описано в CSS и переключается в app.js."""
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "app" / "static"
    css = (static / "styles.css").read_text(encoding="utf-8")
    js = (static / "app.js").read_text(encoding="utf-8")

    assert "--sidebar-width-collapsed" in css
    assert "html.sidebar-collapsed .sidebar" in css
    assert "sidebar-collapsed" in js
    assert "data-sidebar-toggle" in js


def test_sidebar_groups_link_opens_working_page(client):
    """Пункт «Группы» сайдбара ведёт на работающую страницу, а не на 404."""
    _login(client, email="groups-nav-user@example.com")

    page = client.get("/tutor/").text
    start = page.index('<aside class="sidebar"')
    sidebar_html = page[start : page.index("</aside>", start)]
    assert 'href="/tutor/groups"' in sidebar_html
    assert "Группы" in sidebar_html

    response = client.get("/tutor/groups")
    assert response.status_code == 200
    assert "<h1>Группы</h1>" in response.text
    # Пункт подсвечен как активный.
    assert 'nav-item nav-item--active' in response.text
