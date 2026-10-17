"""Тесты: кнопка «Выйти» в сайдбаре, страницы авторизации, 404."""

PASSWORD = "Секретный-Пароль-1"


def _login(client, email="logout-btn@example.com"):
    client.post(
        "/tutor/register",
        data={
            "name": "Выходящий",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )
    return client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )


def test_sidebar_logout_button_posts_to_logout(client):
    """Кнопка «Выйти» в сайдбаре — форма с POST на /tutor/logout."""
    _login(client)
    page = client.get("/tutor/").text
    assert '<form method="post" action="/tutor/logout">' in page


def test_sidebar_logout_works(client):
    """Нажатие «Выйти» действительно завершает сессию."""
    _login(client)
    assert client.get("/tutor/", follow_redirects=False).status_code == 200

    response = client.post("/tutor/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"

    assert client.get("/tutor/", follow_redirects=False).status_code == 303


def test_auth_pages_share_style_without_sidebar(client):
    """Все страницы авторизации — на общем макете auth.html, без сайдбара."""
    for url in ("/tutor/login", "/tutor/register", "/tutor/remember-password"):
        response = client.get(url)
        assert response.status_code == 200, url
        assert 'class="auth"' in response.text, url
        assert 'class="sidebar"' not in response.text, url
        assert "styles.css" in response.text, url


def test_auth_pages_have_labels_and_primary_button(client):
    """У инпутов есть label, кнопки submit оформлены как btn btn--primary."""
    page = client.get("/tutor/login").text
    assert 'class="label"' in page
    assert 'class="btn btn--primary btn--block"' in page
    assert page.count("<label") == 2


def test_404_renders_custom_page(client):
    """Неизвестный маршрут отдаёт HTML-страницу 404 со смешным текстом."""
    response = client.get("/net-takoy-stranitsy")
    assert response.status_code == 404
    assert "404" in response.text
    assert "у этого урока не было учителя" in response.text
    assert "styles.css" in response.text
    # Картинка — inline SVG, без внешних запросов.
    assert '<svg' in response.text


def test_404_is_html_not_json(client):
    response = client.get("/still-missing")
    assert response.headers["content-type"].startswith("text/html")
