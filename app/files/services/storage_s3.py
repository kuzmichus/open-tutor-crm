"""S3-хранилище: приватный бакет и временные ссылки (design D2).

`boto3` синхронный, поэтому клиент собирается один раз и переиспользуется;
вызовы из async-вьюх уходят в `run_in_threadpool` (design D9), иначе один
медленный запрос к S3 блокировал бы event loop воркера.

Ссылка на скачивание — presigned URL на `get_object` со сроком жизни
`files_presign_ttl_seconds`: бакет приватный, и единственный способ отдать
файл — короткоживущая ссылка. `ResponseContentDisposition`/`ResponseContentType`
заставляют браузер скачать файл под исходным именем, а не открыть его
встроенным просмотрщиком (design D7).

Конструктор принимает фабрику клиента: тесты подставляют заглушку и не ходят
в сеть (правило CI «тесты не ходят в сеть»).
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.files.services.storage import Storage

class S3Storage(Storage):
    """Хранилище в S3-совместимом бакете с префиксом ключей."""

    backend = "s3"

    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "",
        presign_ttl_seconds: int = 900,
        client_factory: Callable[[], Any] | None = None,
        region: str = "us-east-1",
        endpoint_url: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
    ) -> None:
        self.bucket = bucket
        # Префикс без ведущего слэша: `uploads/` + ключ, а не `/uploads/`.
        self.prefix = prefix.lstrip("/")
        self.presign_ttl_seconds = presign_ttl_seconds
        self._client_factory = client_factory
        self._client: Any = None
        self._region = region
        self._endpoint_url = endpoint_url
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key

    @property
    def client(self) -> Any:
        """Клиент S3; собирается лениво — импорт boto3 не тянет сеть."""
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory()
            else:
                self._client = self._build_client()
        return self._client

    def _build_client(self) -> Any:
        """Стандартный клиент boto3 по параметрам конфигурации."""
        import boto3

        return boto3.client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint_url or None,
            aws_access_key_id=self._access_key_id or None,
            aws_secret_access_key=self._secret_access_key or None,
        )

    def _object_key(self, key: str) -> str:
        """Ключ объекта в бакете: префикс + ключ приложения."""
        return f"{self.prefix}{key}"

    def save(self, key: str, data: bytes, content_type: str) -> None:
        """Кладёт объект в бакет; существующий объект заменяется."""
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._object_key(key),
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )

    def open(self, key: str) -> bytes:
        """Читает объект целиком; нет объекта — ошибка клиента S3."""
        response = self.client.get_object(
            Bucket=self.bucket, Key=self._object_key(key)
        )
        return response["Body"].read()

    def delete(self, key: str) -> None:
        """Удаляет объект; отсутствующий объект в S3 — не ошибка."""
        self.client.delete_object(
            Bucket=self.bucket, Key=self._object_key(key)
        )

    def exists(self, key: str) -> bool:
        """Есть ли объект по ключу (запрос `head_object`)."""
        try:
            self.client.head_object(
                Bucket=self.bucket, Key=self._object_key(key)
            )
        except Exception:  # noqa: BLE001 — любая ошибка клиента = «нет объекта»
            return False
        return True

    def download_url(
        self, key: str, filename: str, content_type: str
    ) -> str | None:
        """Presigned URL на скачивание вложением под исходным именем."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": self._object_key(key),
                "ResponseContentDisposition": (
                    f'attachment; filename="{filename}"'
                ),
                "ResponseContentType": content_type or "application/octet-stream",
            },
            ExpiresIn=self.presign_ttl_seconds,
        )

    def local_path(self, key: str) -> Path | None:
        """None: объект не на локальном диске — отдаётся по ссылке."""
        return None
