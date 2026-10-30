"""Статика отдаётся с `Cache-Control: no-cache` (всегда ревалидация).

Без заголовка браузер применял эвристическое кэширование: долгоживущая
вкладка htmx-приложения продолжала работать со старым `lessons.js` после
обновления файла — сервер рендерил новую разметку, а Alpine-состояние
нового блока молча не заводилось.
"""

from fastapi.testclient import TestClient

from main import app


def test_static_files_require_revalidation(client: TestClient):
    response = client.get("/static/lessons.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_static_revalidation_returns_304_with_etag(client: TestClient):
    first = client.get("/static/lessons.js")
    etag = first.headers["etag"]
    second = client.get("/static/lessons.js", headers={"If-None-Match": etag})
    assert second.status_code == 304
