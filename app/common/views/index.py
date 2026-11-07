"""Корень приложения: опубликованный лендинг либо редирект в кабинет.

В сингл-режиме с опубликованной страницей `GET /` отдаёт `index.html`
как обычный статический файл: серверной подстановки данных нет, вся
динамика входов — клиентская (задача 3). Файл читается с диска при
каждом запросе, поэтому `Cache-Control: no-cache` обязателен — иначе
свежая публикация не была бы видна сразу.

Без публикации (или в мульти-режиме) — прежнее поведение: 303 на
`/tutor/`.
"""

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.landing.services.access import published_landing

router = APIRouter()

# Страница публикуется заново при каждой правке, поэтому браузер обязан
# сверять её с сервером: без этого обновление лендинга не видно сразу.
_LANDING_HEADERS = {"Cache-Control": "no-cache"}


@router.get("/", response_class=RedirectResponse)
def index() -> Response:
    """Главная страница: лендинг, если опубликован, иначе 303 на `/tutor/`."""
    page = published_landing()
    if page is None:
        return RedirectResponse(url="/tutor/", status_code=303)
    return FileResponse(
        page,
        media_type="text/html",
        headers=_LANDING_HEADERS,
    )
