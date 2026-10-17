"""Конфигурация приложения.

Все параметры можно переопределить переменными окружения (или .env),
например:  DATABASE_URL=sqlite:///./tutor.db
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Open Tutor CRM"
    database_url: str = "sqlite:///./tutor.db"


settings = Settings()
