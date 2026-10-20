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


@pytest.fixture()
def student_factory(tutor_factory):
    """Создаёт ученика в тестовой БД и возвращает его id.

    `tutor_id` по умолчанию берётся у свежесозданного репетитора, поэтому
    тест, которому важен только ученик, не обязан заводить репетитора сам.
    Значения по умолчанию уникальны, чтобы фабрику можно было звать подряд.
    """

    def _create(
        tutor_id: str | None = None,
        first_name: str | None = None,
        kind: str = "child",
        **extra,
    ):
        from uuid import uuid4

        from app.database import SessionLocal
        from app.student.models.student import Student

        if tutor_id is None:
            tutor_id = tutor_factory()
        if first_name is None:
            first_name = f"Ученик{uuid4().hex[:8]}"

        with SessionLocal() as session:
            student = Student(tutor_id=tutor_id, first_name=first_name, kind=kind, **extra)
            session.add(student)
            session.commit()
            return student.id

    return _create


@pytest.fixture()
def group_factory(tutor_factory):
    """Создаёт группу в тестовой БД и возвращает её id.

    `tutor_id` по умолчанию берётся у свежесозданного репетитора; имя по
    умолчанию уникально, чтобы фабрику можно было звать подряд.
    """

    def _create(
        tutor_id: str | None = None,
        name: str | None = None,
        **extra,
    ):
        from uuid import uuid4

        from app.database import SessionLocal
        from app.group.models.group import Group

        if tutor_id is None:
            tutor_id = tutor_factory()
        if name is None:
            name = f"Группа {uuid4().hex[:8]}"

        with SessionLocal() as session:
            group = Group(tutor_id=tutor_id, name=name, **extra)
            session.add(group)
            session.commit()
            return group.id

    return _create


@pytest.fixture()
def group_member_factory(group_factory, student_factory):
    """Создаёт членство «ученик ∈ группа» и возвращает его id."""

    def _create(
        group_id: str | None = None,
        student_id: str | None = None,
        **extra,
    ):
        from app.database import SessionLocal
        from app.group.models.group import Group
        from app.group.models.group_member import GroupMember

        if group_id is None:
            group_id = group_factory()
        if student_id is None:
            # Ученик по умолчанию — тот же репетитор, что и у группы.
            with SessionLocal() as session:
                group = session.get(Group, group_id)
            student_id = student_factory(tutor_id=group.tutor_id)

        with SessionLocal() as session:
            member = GroupMember(group_id=group_id, student_id=student_id, **extra)
            session.add(member)
            session.commit()
            return member.id

    return _create


@pytest.fixture()
def contact_factory(tutor_factory):
    """Создаёт контакт взрослого в тестовой БД и возвращает его id.

    `tutor_id` по умолчанию — у свежесозданного репетитора; передайте его
    явно, если контакт должен принадлежать тому же репетитору, что и ученик.
    """

    def _create(
        tutor_id: str | None = None,
        full_name: str | None = None,
        **extra,
    ):
        from uuid import uuid4

        from app.database import SessionLocal
        from app.student.models.contact import Contact

        if tutor_id is None:
            tutor_id = tutor_factory()
        if full_name is None:
            full_name = f"Контакт {uuid4().hex[:8]}"

        with SessionLocal() as session:
            contact = Contact(tutor_id=tutor_id, full_name=full_name, **extra)
            session.add(contact)
            session.commit()
            return contact.id

    return _create
