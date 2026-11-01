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


settings = Settings()
