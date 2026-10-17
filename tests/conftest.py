"""Фикстуры pytest: изолированная in-memory БД и TestClient."""

import os

# Переопределяем URL БД ДО импорта приложения, чтобы engine строился на тестовой базе.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401  # регистрация моделей на Base.metadata
from app.database import Base, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
