"""Картинки лендинга: публичная отдача и управление из редактора.

`GET /landing-assets/{filename}` — публичный маршрут. Ассеты и так встроены
в опубликованную страницу, поэтому отдельного доступа не требуют. Имя
проверяется строгим шаблоном `ASSET_NAME_PATTERN` (`uuid4` и расширение
картинки): заодно это защита от обхода каталога, потому что имя приходит
из URL. Не прошедшее шаблон имя — 404, как и отсутствующий файл: чужая
или несуществующая картинка неотличимы. Кэш долгий и `immutable`: имя
ассета — uuid, содержимое под одним именем не меняется.

`POST /tutor/landing/assets` принимает multipart-загрузку GrapesJS (поле
`files` или `files[]` в зависимости от `multiUpload`), проверяет имя,
расширение, размер и магические байты растров, затем пишет каждый файл под
сгенерированным именем. Ответ — `{"data": [{src, type}]}`: именно этот
формат `autoAdd` GrapesJS кладёт в коллекцию ассетов.

`DELETE /tutor/landing/assets/{filename}` удаляет файл с диска. Имя
проверяется тем же шаблоном, что и на публичной отдаче; невалидное имя —
404. Отсутствующий файл — не ошибка: повторное удаление идемпотентно.

Оба управляющих роута требуют сессию репетитора и доступны только в
сингл-режиме: в мульти-установке лендинга нет, и вьюхи отвечают 404 до
любого обращения к диску.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response

from app.common.access import require_tutor_id
from app.config import settings
from app.files.services.upload import (
    original_name,
    read_limited,
    validate_upload,
)
from app.landing.services.access import landing_enabled
from app.landing.services.storage import (
    ALLOWED_ASSET_EXTENSIONS,
    get_storage,
    is_asset_name,
    is_valid_asset_content,
)

router = APIRouter()

# Адрес загрузки для конфига Asset Manager GrapesJS и префикс ссылок,
# которые попадают в HTML страницы. Ссылки абсолютные: `/` и предпросмотр
# показывают одну и ту же страницу, поэтому относительный путь сломался бы
# при открытии редактора по другому адресу.
ASSETS_URL = "/tutor/landing/assets"
ASSET_URL_PREFIX = "/landing-assets/"

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

# Управляющие ответы не должны кэшироваться: список ассетов меняется.
_NO_STORE = {"Cache-Control": "no-store"}

_ALLOWED_EXTENSIONS = tuple(sorted(ALLOWED_ASSET_EXTENSIONS))


def _ensure_landing_enabled() -> None:
    """404 в мульти-режиме: фича существует только в сингл-установке."""
    if not landing_enabled():
        raise HTTPException(status_code=404)


def _error(status_code: int, message: str) -> JSONResponse:
    """Понятное человеку сообщение об отказе в формате JSON."""
    return JSONResponse(
        {"error": message}, status_code=status_code, headers=_NO_STORE
    )


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


@router.post(ASSETS_URL)
async def landing_assets_upload(
    request: Request,
    tutor_id: str = Depends(require_tutor_id),
) -> JSONResponse:
    """Загружает картинки из Asset Manager GrapesJS.

    Валидируется весь набор до записи: если хотя бы один файл не прошёл
    проверку, на диск не попадает ничего — иначе отказ на втором файле
    оставил бы первый «осиротевшим» ассетом без ссылки в ответе.
    """
    _ensure_landing_enabled()

    form = await request.form()
    # GrapesJS при `multiUpload` шлёт поле `files[]`, без него — `files`.
    # Принимаем оба: имя поля задаёт библиотека, а не мы.
    uploads = [
        value
        for _, value in form.multi_items()
        if getattr(value, "filename", "")
    ]
    if not uploads:
        return _error(status.HTTP_400_BAD_REQUEST, "Выберите файл для загрузки.")

    prepared: list[tuple[str, bytes]] = []
    for upload in uploads:
        filename = upload.filename or ""
        errors = validate_upload(
            filename,
            0,
            allowed=_ALLOWED_EXTENSIONS,
            max_bytes=settings.max_file_bytes,
        )
        if errors:
            return _error(status.HTTP_400_BAD_REQUEST, errors[0])

        data = await read_limited(upload, max_bytes=settings.max_file_bytes)
        if data is None:
            return _error(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"Файл «{original_name(filename)}» больше "
                f"{settings.files_max_size_mb} МБ.",
            )
        if not data:
            return _error(
                status.HTTP_400_BAD_REQUEST,
                f"Файл «{original_name(filename)}» пустой.",
            )
        if not is_valid_asset_content(filename, data):
            return _error(
                status.HTTP_400_BAD_REQUEST,
                f"Файл «{original_name(filename)}» не является картинкой: "
                "содержимое не совпадает с расширением.",
            )
        prepared.append((filename, data))

    storage = get_storage()
    saved = [
        {
            "src": f"{ASSET_URL_PREFIX}{storage.save_asset(filename, data)}",
            "type": "image",
        }
        for filename, data in prepared
    ]
    return JSONResponse({"data": saved}, headers=_NO_STORE)


@router.delete(f"{ASSETS_URL}/{{filename}}")
def landing_asset_delete(
    filename: str,
    tutor_id: str = Depends(require_tutor_id),
) -> Response:
    """Удаляет картинку с диска; невалидное имя — 404."""
    _ensure_landing_enabled()
    if not is_asset_name(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    get_storage().remove_asset(filename)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)


def _extension(path: Path) -> str:
    """Расширение файла без точки — ключ `_MEDIA_TYPES`."""
    return path.suffix.lstrip(".").lower()