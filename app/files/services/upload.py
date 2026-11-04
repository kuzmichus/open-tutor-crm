"""Загрузка файла: валидация, ключ объекта, запись в хранилище (design D4, D5).

Сервис не знает про FastAPI (правило AGENTS.md): `UploadFile` сюда приходит
как объект с `filename`, `content_type` и асинхронным `read(size)`, а ошибки
возвращаются списком сообщений в стиле форм проекта.

Тело файла читается чанками с жёстким обрывом при превышении лимита: читать
`UploadFile` целиком нельзя — несколько файлов по 20 МБ в одном запросе
съели бы память воркера.

Ключ объекта формирует сервер: `<tutor_id>/<32 hex><ext>`. Имя пользователя в
ключ не попадает — ключ это адрес объекта, а не данные; исходное имя живёт в
метаданных и уходит в `Content-Disposition`.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.files.models.stored_file import (
    MAX_ORIGINAL_NAME_LENGTH,
    StoredFile,
)
from app.files.services.storage import Storage

# Размер порции чтения: компромисс между числом системных вызовов и
# памятью — 1 МБ на файл в полёте.
CHUNK_SIZE = 1024 * 1024

# Content type по расширению для случаев, когда браузер его не прислал или
# прислал общий `application/octet-stream`. Нужен и локальной отдаче, и S3
# (`ResponseContentType`).
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "odt": "application/vnd.oasis.opendocument.text",
    "rtf": "application/rtf",
    "txt": "text/plain",
    "md": "text/markdown",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "csv": "text/csv",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    "odp": "application/vnd.oasis.opendocument.presentation",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "heic": "image/heic",
    "zip": "application/zip",
    "7z": "application/x-7z-compressed",
}

DEFAULT_CONTENT_TYPE = "application/octet-stream"

def extension_of(filename: str) -> str:
    """Расширение файла без точки в нижнем регистре; нет расширения — ''."""
    return Path(filename).suffix.lstrip(".").lower()

def content_type_for(filename: str, declared: str | None) -> str:
    """Тип содержимого: по расширению, если браузер прислал общий тип.

    Браузер может прислать пустую строку или `application/octet-stream` —
    такой тип ничего не говорит, и файл открывался бы без иконки и с
    неверным `Content-Type` при скачивании.
    """
    if declared and declared != DEFAULT_CONTENT_TYPE:
        return declared[:128]
    return CONTENT_TYPES.get(extension_of(filename), DEFAULT_CONTENT_TYPE)

def validate_upload(
    filename: str,
    size: int,
    *,
    allowed: tuple[str, ...] | None = None,
    max_bytes: int | None = None,
) -> list[str]:
    """Ошибки загружаемого файла: имя, расширение, размер.

    Проверки идут до чтения тела: файл запрещённого расширения не должен
    занимать память и место в хранилище.
    """
    allowed = settings.allowed_extensions if allowed is None else allowed
    max_bytes = settings.max_file_bytes if max_bytes is None else max_bytes
    errors: list[str] = []

    name = (filename or "").strip()
    if not name:
        return ["Выберите файл для загрузки."]

    ext = extension_of(name)
    if not ext:
        errors.append(f"Файл «{name}» должен иметь расширение.")
    elif ext not in allowed:
        errors.append(
            f"Файл «{name}»: недопустимый формат. "
            f"Разрешены: {', '.join(allowed)}."
        )

    if size > max_bytes:
        errors.append(
            f"Файл «{name}» больше {settings.files_max_size_mb} МБ."
        )
    return errors

def build_key(tutor_id: str, filename: str) -> str:
    """Ключ объекта: `<tutor_id>/<32 hex><ext>` — без имени пользователя."""
    ext = extension_of(filename)
    suffix = f".{ext}" if ext else ""
    return f"{tutor_id}/{uuid4().hex}{suffix}"

def original_name(filename: str) -> str:
    """Исходное имя файла для метаданных: только базовое имя и лимит длины.

    `Path(...).name` отбрасывает каталоги из имени: браузер присылает только
    имя, но старая версия могла прислать путь, и `C:\\tmp\\x.pdf` не должен
    попадать в `Content-Disposition`.
    """
    name = Path(filename or "").name.strip() or "file"
    return name[:MAX_ORIGINAL_NAME_LENGTH]

async def read_limited(
    upload,
    *,
    max_bytes: int,
    read: Callable[[int], Awaitable[bytes]] | None = None,
) -> bytes | None:
    """Читает тело файла чанками; None — файл больше лимита.

    Чтение обрывается сразу, как только суммарный размер превысил лимит:
    ждать конца тела нельзя — именно этим и защищаемся от больших файлов.
    """
    reader = read or upload.read
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await reader(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)

async def save_upload(
    db: Session,
    tutor_id: str,
    upload,
    storage: Storage | None = None,
) -> tuple[StoredFile | None, list[str]]:
    """Сохраняет один файл: объект в хранилище и строку метаданных.

    Возвращает `(файл, ошибки)`: при ошибке файл не создан, а объект в
    хранилище не записан. Строка в БД добавляется, но не коммитится —
    коммит делает вызывающая вьюха вместе с сохранением ДЗ, чтобы ошибка
    другого файла откатила весь набор (design D5).
    """
    filename = getattr(upload, "filename", "") or ""
    errors = validate_upload(filename, 0)
    if errors:
        return None, errors

    data = await read_limited(upload, max_bytes=settings.max_file_bytes)
    if data is None:
        return None, [
            f"Файл «{original_name(filename)}» больше "
            f"{settings.files_max_size_mb} МБ."
        ]

    name = original_name(filename)
    # Размер известен только после чтения: пустой файл допустим, но
    # проверить его нулевой размер повторно не нужно — лимит уже соблюдён.
    content_type = content_type_for(name, getattr(upload, "content_type", None))
    key = build_key(tutor_id, name)
    store = storage or _default_storage()
    store.save(key, data, content_type)

    stored = StoredFile(
        tutor_id=tutor_id,
        backend=store.backend,
        storage_key=key,
        original_name=name,
        content_type=content_type,
        size=len(data),
    )
    db.add(stored)
    return stored, []

def _default_storage() -> Storage:
    """Хранилище по конфигурации; импорт внутри — разрыв цикла модулей."""
    from app.files.services.storage_factory import get_storage

    return get_storage()
