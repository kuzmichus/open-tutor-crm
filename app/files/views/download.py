"""Скачивание файла (спека file-storage, design D6, D7).

Один адрес `GET /files/{file_id}` на оба бэкенда: вьюха спрашивает у
хранилища временную ссылку и, если её нет, отдаёт файл сама.

- S3: 302 на presigned URL — файл отдаёт бакет, TTL ограничен
  `FILES_PRESIGN_TTL_SECONDS`.
- локально: `FileResponse` с проверкой сессии (доступ уже проверен
  `resolve_downloadable_file`) и защитными заголовками.

`Content-Disposition: attachment` и `X-Content-Type-Options: nosniff`
обязательны: загруженный SVG или HTML иначе открылся бы в контексте домена
приложения и получил доступ к сессионной cookie (stored XSS). `no-store` —
потому что файл приватный и не должен оставаться в кэше браузера.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.files.services.access import resolve_downloadable_file
from app.files.services.storage_factory import storage_for_backend

router = APIRouter()

# Заголовки локальной отдачи: вложение, без сниффинга типа, без кэша.
_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}

@router.get("/files/{file_id}")
def download_file(
    file_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Отдаёт файл актору с доступом; остальным — 404.

    Синхронная вьюха: `boto3` и чтение с диска синхронны, и в async-вьюхе их
    пришлось бы заворачивать в `run_in_threadpool` (design D9). Starlette
    выполняет sync-эндпоинты в пуле потоков — то же поведение без обёрток.
    """
    file = resolve_downloadable_file(db, file_id, request)
    storage = storage_for_backend(file.backend)
    url = storage.download_url(file.storage_key, file.original_name, file.content_type)
    if url is not None:
        return RedirectResponse(url=url, status_code=302, headers=_PRIVATE_HEADERS)

    path = storage.local_path(file.storage_key)
    if path is None or not path.is_file():
        # Метаданные есть, объекта нет: строка от оборванной загрузки или
        # ручного удаления файла с диска — для пользователя это «нет файла».
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return FileResponse(
        path,
        media_type=file.content_type,
        filename=file.original_name,
        headers=_PRIVATE_HEADERS,
    )
