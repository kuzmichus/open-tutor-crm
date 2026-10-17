"""Подключение к базе данных: движок, сессии и декларативная база.

В тестах URL переопределяется через переменную окружения DATABASE_URL
(например, in-memory SQLite), поэтому всё строится при импорте.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

_DATABASE_URL = settings.database_url


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _pool_class(url: str):
    if ":memory:" in url:
        # In-memory SQLite разделяет одно соединение между всеми сессиями.
        return StaticPool
    return None


engine: Engine = create_engine(
    _DATABASE_URL,
    connect_args=_connect_args(_DATABASE_URL),
    poolclass=_pool_class(_DATABASE_URL),
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Декларативная база для всех ORM-моделей."""


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет (удобно для локальной разработки)."""
    from app import models  # noqa: F401  # регистрация моделей на Base.metadata

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI-зависимость: сессия на время запроса."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
