"""Фикстуры pytest: изолированная in-memory БД и TestClient."""

import os

# Переопределяем URL БД ДО импорта приложения, чтобы engine строился на тестовой базе.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401  # регистрация моделей на Base.metadata
from app.database import Base, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _database():
    """Изолированная БД на каждый тест (in-memory, общий StaticPool-коннект)."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# Заглушка для password_hash: страницам-спискам пароль не нужен по-настоящему.
_PLACEHOLDER_PASSWORD_HASH = "pbkdf2_sha256$1$placeholder$placeholder"


@pytest.fixture()
def tutor_factory():
    """Создаёт репетитора в тестовой БД и возвращает его id.

    Для тестов авторизации передайте `password` — он будет захеширован
    через `PasswordHasher`; для страниц достаточно email/имени.
    БД в тестах общая на сессию, поэтому email по умолчанию уникален для
    каждого вызова (передайте `email`, чтобы задать его явно).
    """

    def _create(
        name: str = "Тестовый Тьютор",
        email: str | None = None,
        password: str | None = None,
        password_hash: str | None = None,
        **extra,
    ):
        from uuid import uuid4

        from app.database import SessionLocal
        from app.tutor.models.tutor import Tutor

        if email is None:
            email = f"tutor-{uuid4().hex[:12]}@example.com"

        if password_hash is None:
            if password is not None:
                from app.tutor.services.password_hasher import PasswordHasher

                password_hash = PasswordHasher().hash(password)
            else:
                password_hash = _PLACEHOLDER_PASSWORD_HASH

        with SessionLocal() as session:
            tutor = Tutor(name=name, email=email, password_hash=password_hash, **extra)
            session.add(tutor)
            session.commit()
            return tutor.id

    return _create
