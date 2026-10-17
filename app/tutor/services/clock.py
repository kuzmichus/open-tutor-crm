"""Время в сервисах модуля tutor.

SQLite возвращает naive-даты (теряет tzinfo), поэтому значения из БД
нормализуются к UTC через `as_utc` перед сравнением с `utcnow()`.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Текущий момент в UTC."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Приводит дату к UTC; naive трактуется как UTC (формат хранения SQLite)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
