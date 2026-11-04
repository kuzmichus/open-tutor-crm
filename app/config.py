"""Конфигурация приложения.

Все параметры можно переопределить переменными окружения (или .env),
например:  DATABASE_URL=sqlite:///./tutor.db

Загрузка файлов настраивается группой `FILES_*`/`S3_*`: хранилище выбирается
переменной `FILES_BACKEND` — локальный каталог сервера или S3-совместимый
бакет. Остальные параметры группы (лимит размера, список расширений, TTL
временной ссылки) действуют при любом хранилище.
"""

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Расширения по умолчанию: документы и картинки, которые реально приносят
# на урок. Список — только данные, проверка расширения живёт в сервисе
# загрузки (`app/files/services/upload.py`).
DEFAULT_ALLOWED_EXTENSIONS = (
    "pdf,doc,docx,odt,rtf,txt,md,"
    "xls,xlsx,ods,csv,"
    "ppt,pptx,odp,"
    "jpg,jpeg,png,gif,webp,heic,"
    "zip,7z"
)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Open Tutor CRM"
    database_url: str = "sqlite:///./tutor.db"
    # Проверка TLS-сертификатов Bot API мессенджеров. Сертификат
    # platform-api2.max.ru подписан корнем Минцифры (ГОСТ), которого нет
    # в системных хранилищах; на таких машинах флаг ставят в false.
    messenger_tls_verify: bool = True
    # OAuth-клиент Google Календаря: креды задаёт владелец сервера один
    # раз в окружении, репетитор только нажимает «Подключить Google».
    # Пустые значения — интеграция выключена, карточка в профиле объясняет
    # причину (design D1).
    google_client_id: str = ""
    google_client_secret: str = ""
    # Внешний адрес callback. Пусто — строится из запроса; за прокси
    # request.base_url может дать http:// и внутренний хост, тогда Google
    # отклонит обмен кода (design D9).
    google_redirect_uri: str = ""
    # Общий выключатель синхронизации: false — хуки вьюх ничего не пишут
    # в Google, остальное приложение работает как обычно.
    google_calendar_sync: bool = True

    # --- Загрузка файлов ---------------------------------------------------
    # Куда писать объекты: `local` — каталог `files_local_root` на сервере,
    # `s3` — S3-совместимый бакет. Дефолт `local`: установка без S3
    # работает «из коробки», а бакет — осознанный выбор администратора.
    files_backend: Literal["local", "s3"] = "local"
    files_local_root: str = "./files"
    files_max_size_mb: int = 20
    # Список расширений через запятую: один параметр вместо массива в env.
    files_allowed_extensions: str = DEFAULT_ALLOWED_EXTENSIONS
    # Срок жизни presigned URL (только для S3): ссылка живёт после отзыва
    # доступа, поэтому по умолчанию короткий — 15 минут.
    files_presign_ttl_seconds: int = 900

    # --- S3 (читаются только при files_backend='s3') -----------------------
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    # Адрес S3-совместимого хранилища (MinIO, Selectel); пусто — AWS.
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_prefix: str = "uploads/"

    @model_validator(mode="after")
    def _check_files_settings(self) -> "Settings":
        """Неполная конфигурация S3 — ошибка старта, а не падение на загрузке.

        Проверка здесь, а не в фабрике хранилища: приложение не должно
        подниматься, если выбран бэкенд, к которому нельзя подключиться —
        иначе первая же загрузка файла упадёт на запросе пользователя.
        """
        if self.files_max_size_mb <= 0:
            raise ValueError("FILES_MAX_SIZE_MB должен быть больше нуля")
        if self.files_presign_ttl_seconds <= 0:
            raise ValueError("FILES_PRESIGN_TTL_SECONDS должен быть больше нуля")
        if not self.allowed_extensions:
            raise ValueError("FILES_ALLOWED_EXTENSIONS не может быть пустым")
        if self.files_backend == "s3":
            missing = [
                name
                for name, value in (
                    ("S3_BUCKET", self.s3_bucket),
                    ("S3_ACCESS_KEY_ID", self.s3_access_key_id),
                    ("S3_SECRET_ACCESS_KEY", self.s3_secret_access_key),
                )
                if not value.strip()
            ]
            if missing:
                raise ValueError(
                    "FILES_BACKEND=s3 требует параметров: " + ", ".join(missing)
                )
        return self

    @property
    def allowed_extensions(self) -> tuple[str, ...]:
        """Разрешённые расширения без точки, в нижнем регистре.

        `PDF, .Docx` из env нормализуется к `('pdf', 'docx')`: регистр и
        ведущая точка в настройках — не повод отказывать файлу.
        """
        return tuple(
            part.strip().lstrip(".").lower()
            for part in self.files_allowed_extensions.split(",")
            if part.strip()
        )

    @property
    def max_file_bytes(self) -> int:
        """Лимит размера файла в байтах (из мегабайт в env)."""
        return self.files_max_size_mb * 1024 * 1024

settings = Settings()
