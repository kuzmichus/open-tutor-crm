"""Адрес callback для OAuth: один и тот же в ссылке согласия и в обмене кода.

Google сверяет `redirect_uri` побайтово: если при обмене кода адрес
отличается от того, что был в ссылке согласия, ответ — `redirect_uri_mismatch`.
Поэтому адрес строится здесь и передаётся в оба вызова (`oauth.py`).

Основной способ — переменная `GOOGLE_REDIRECT_URI`: за прокси и в
контейнере `request.base_url` может дать `http://` и внутренний хост,
а Google принимает только адрес, зарегистрированный в Google Cloud
Console (design D9). Пустое значение — адрес собирается из запроса:
удобно для локальной разработки на `http://localhost:8000`.
"""

from fastapi import Request

from app.config import settings

# Путь callback в приложении; он же — хвост адреса, собранного из запроса.
CALLBACK_PATH = "/tutor/profile/google/callback"

def redirect_uri(request: Request) -> str:
    """Внешний адрес callback: из окружения, иначе из запроса."""
    if settings.google_redirect_uri:
        return settings.google_redirect_uri
    return str(request.base_url).rstrip("/") + CALLBACK_PATH
