"""Тесты корневого редиректа и htmx-фрагмента времени."""


def test_index_redirects_to_tutor_home(client):
    """Корень отвечает 303 на `/tutor/`, без сессии цепочка ведёт на вход.

    Два шага проверяются в одном тесте: второй (`/tutor/` → `/tutor/login`)
    имеет смысл только как продолжение первого редиректа.
    """
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/"

    follow = client.get(response.headers["location"], follow_redirects=False)
    assert follow.status_code == 303
    assert follow.headers["location"] == "/tutor/login"


def test_clock_fragment_returns_time(client):
    """Без сессии фрагмент всё равно отдаёт время, а не редирект."""
    response = client.get("/time", follow_redirects=False)
    assert response.status_code == 200
    assert response.text.strip()


def test_clock_fragment_shows_time_in_tutor_zone(client, tutor_factory, monkeypatch):
    """Спека (задача 8.3): `/time` форматирует время в зоне педагога.

    Момент 06:00 UTC у репетитора в UTC+04 — это 10:00 его настенного
    времени: часы в шапке не должны показывать серверное время.
    """
    from datetime import UTC, datetime

    fixed = datetime(2026, 10, 22, 6, 0, tzinfo=UTC)
    monkeypatch.setattr("app.common.services.tutor_time.utcnow", lambda: fixed)

    password = "Секретный-Пароль-1"
    tutor_factory(
        email="clock-tz@example.com",
        password=password,
        timezone="Europe/Ulyanovsk",
    )
    client.post(
        "/tutor/login",
        data={"email": "clock-tz@example.com", "password": password},
        follow_redirects=False,
    )

    response = client.get("/time", follow_redirects=False)

    assert response.status_code == 200
    assert response.text.strip() == "2026-10-22 10:00:00"


def test_htmx_is_served_locally(client):
    """htmx подключается локально (без CDN/SRI) и отдаётся статикой."""
    page = client.get("/tutor/login")
    assert "/static/htmx.min.js" in page.text
    assert "unpkg.com" not in page.text

    asset = client.get("/static/htmx.min.js")
    assert asset.status_code == 200
    assert "htmx" in asset.text
