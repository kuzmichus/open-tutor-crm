"""Конфигурация приложения.

Все параметры можно переопределить переменными окружения (или .env),
например:  DATABASE_URL=sqlite:///./tutor.db
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Open Tutor CRM"
    database_url: str = "sqlite:///./tutor.db"
    # Проверка TLS-сертификатов Bot API мессенджеров. Сертификат
    # platform-api2.max.ru подписан корнем Минцифры (ГОСТ), которого нет
    # в системных хранилищах; на таких машинах флаг ставят в false.
    messenger_tls_verify: bool = True


settings = Settings()
