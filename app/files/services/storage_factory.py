"""Фабрика хранилища: единственное место, знающее про env (design D3).

Сервисы получают готовое хранилище функцией `get_storage()`, а не набором
настроек: выбор бэкенда не растекается по коду, а тесты сбрасывают кэш
`get_storage.cache_clear()` и подменяют `settings`.

Кэш на процесс: клиент S3 дорог в сборке, а локальный корень не меняется
между запросами. Смена env требует перезапуска — как и остальные настройки
приложения.
"""

from functools import lru_cache

from app.config import settings
from app.files.services.storage import Storage
from app.files.services.storage_local import LocalStorage
from app.files.services.storage_s3 import S3Storage

def storage_for_backend(backend: str) -> Storage:
    """Хранилище конкретного бэкенда по текущим настройкам.

    Нужно старым файлам: строка помнит свой бэкенд, и файл читается оттуда,
    куда был записан, даже если env уже переключён (design D1).
    """
    if backend == "s3":
        return S3Storage(
            settings.s3_bucket,
            prefix=settings.s3_prefix,
            presign_ttl_seconds=settings.files_presign_ttl_seconds,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
        )
    return LocalStorage(settings.files_local_root)

@lru_cache(maxsize=1)
def get_storage() -> Storage:
    """Хранилище по текущей конфигурации: `local` или `s3`."""
    return storage_for_backend(settings.files_backend)
