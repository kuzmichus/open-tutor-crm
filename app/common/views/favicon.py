"""Отдача `/favicon.ico` из корня сайта.

Зачем маршрут. Браузеры, поисковые роботы и внешние сервисы (аватары
ссылок в мессенджерах, превью в закладках) запрашивают `/favicon.ico`
напрямую, не читая `<link rel="icon">`. Без маршрута такой запрос
попадает в обработчик 404 и возвращает HTML-страницу — сервис показывает
битую иконку, а в логах копится шум.

Файл — тот же, что отдаёт `/static/favicons/favicon.ico` (собирается
`scripts/build_favicons.py`), поэтому набор остаётся в одном месте:
статический mount отдаёт его страницам, а этот маршрут закрывает запросы
по корневому адресу.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

FAVICON = Path(__file__).resolve().parents[2] / "static" / "favicons" / "favicon.ico"

@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    """Иконка сайта для запросов по корневому адресу.

    `no-cache` — та же политика, что у остальной статики
    (`app/common/static_files.py`): браузер хранит файл, но сверяет его
    с сервером, поэтому обновление знака подхватывается без сброса кэша.
    """
    return FileResponse(
        FAVICON,
        media_type="image/vnd.microsoft.icon",
        headers={"Cache-Control": "no-cache"},
    )
