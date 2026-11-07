"""Отдача картинок лендинга: `GET /landing-assets/{filename}`.

Ассеты публичны — они и так встроены в опубликованную страницу. Имя
проверяется строгим шаблоном `ASSET_NAME_PATTERN` (`uuid4` и расширение
картинки): заодно это защита от обхода каталога, потому что имя приходит
из URL. Не прошедшее шаблон имя — 404, как и отсутствующий файл: чужая
или несуществующая картинка неотличимы.

Кэш долгий и `immutable`: имя ассета — uuid, содержимое под одним именем
не меняется, поэтому повторный запрос не должен доходить до сервера.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.landing.services.storage import get_storage, is_asset_name

router = APIRouter()

# Тип содержимого по расширению: `mimetypes` на разных системах знает SVG
# по-разному, а отдавать картинку как `text/plain` нельзя.
_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}

# Имя ассета неизменно, поэтому кэш на год.
_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}


@router.get("/landing-assets/{filename}")
def landing_asset(filename: str) -> FileResponse:
    """Отдаёт картинку лендинга; неизвестное имя — 404."""
    if not is_asset_name(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    path = get_storage().asset_path(filename)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return FileResponse(
        path,
        media_type=_MEDIA_TYPES[_extension(path)],
        headers=_CACHE_HEADERS,
    )


def _extension(path: Path) -> str:
    """Расширение файла без точки — ключ `_MEDIA_TYPES`."""
    return path.suffix.lstrip(".").lower()
