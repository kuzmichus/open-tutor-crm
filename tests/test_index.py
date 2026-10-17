"""Тесты главной страницы и htmx-фрагмента времени."""


def test_index_contains_hello_world(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Hello world" in response.text


def test_index_has_htmx_clock(client):
    response = client.get("/")
    assert 'id="clock"' in response.text
    assert 'hx-get="/time"' in response.text
    assert 'hx-trigger="every 1s"' in response.text


def test_clock_fragment_returns_time(client):
    response = client.get("/time")
    assert response.status_code == 200
    assert response.text.strip()


def test_htmx_is_served_locally(client):
    """htmx подключается локально (без CDN/SRI) и отдаётся статикой."""
    page = client.get("/")
    assert "/static/htmx.min.js" in page.text
    assert "unpkg.com" not in page.text

    asset = client.get("/static/htmx.min.js")
    assert asset.status_code == 200
    assert "htmx" in asset.text
