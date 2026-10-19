"""Тесты корневого редиректа и htmx-фрагмента времени."""


def test_index_redirects_to_tutor_home(client):
    """Корень отвечает 303 на `/tutor/`."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/"


def test_index_redirect_chain_without_session(client):
    """Без сессии цепочка `/` → `/tutor/` → `/tutor/login` заканчивается входом."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    follow = client.get(response.headers["location"], follow_redirects=False)
    assert follow.status_code == 303
    assert follow.headers["location"] == "/tutor/login"


def test_home_contains_hello_world(client):
    """Заглушка дашборда с «Hello world» переехала на `/tutor/`."""
    from tests.test_home import _login

    _login(client, email="hello@example.com")
    response = client.get("/tutor/")
    assert response.status_code == 200
    assert "Hello world" in response.text


def test_home_has_htmx_clock(client):
    """Часы hx-get=/time отдаются на `/tutor/`."""
    from tests.test_home import _login

    _login(client, email="clock@example.com")
    response = client.get("/tutor/")
    assert 'id="clock"' in response.text
    assert 'hx-get="/time"' in response.text
    assert 'hx-trigger="every 1s"' in response.text


def test_clock_fragment_returns_time(client):
    response = client.get("/time")
    assert response.status_code == 200
    assert response.text.strip()


def test_htmx_is_served_locally(client):
    """htmx подключается локально (без CDN/SRI) и отдаётся статикой."""
    page = client.get("/tutor/login")
    assert "/static/htmx.min.js" in page.text
    assert "unpkg.com" not in page.text

    asset = client.get("/static/htmx.min.js")
    assert asset.status_code == 200
    assert "htmx" in asset.text
