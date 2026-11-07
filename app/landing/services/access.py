"""Публичный доступ к лендингу: включена ли фича и что отдавать с `/`.

Лендинг существует только в сингл-режиме: в мульти-установке публичной
страницы репетитора нет, и корень по-прежнему ведёт в личный кабинет.

`settings` читается в момент вызова, а не при импорте: тесты подменяют
значение через `monkeypatch`, а владелец сервера меняет режим переменной
окружения и перезапуском приложения (как `registration_mode`).
"""

from pathlib import Path

from app.config import settings
from app.landing.services.storage import get_storage


def landing_enabled() -> bool:
    """True, если фича лендинга включена (сингл-режим)."""
    return settings.single_mode


def published_landing() -> Path | None:
    """Путь к опубликованной странице либо `None` — отдавать нечего.

    `None` в двух случаях: фича выключена (мульти-режим) или страница ещё
    не публиковалась. Вьюха корня в обоих случаях отвечает прежним
    редиректом на `/tutor/`.
    """
    if not landing_enabled():
        return None
    storage = get_storage()
    return storage.index_path if storage.has_published() else None
