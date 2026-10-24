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

    `timezone` по умолчанию `UTC`: тесты не должны зависеть от системной
    зоны машины, а зона `UTC` делает настенное время из формы равным
    хранимому. Передайте `timezone=None` или другую зону явно, если тест
    проверяет fallback или конкретную зону (спека tutor-timezone).
    """

    def _create(
        name: str = "Тестовый Тьютор",
        email: str | None = None,
        password: str | None = None,
        password_hash: str | None = None,
        timezone: str | None = "UTC",
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
            tutor = Tutor(
                name=name,
                email=email,
                password_hash=password_hash,
                timezone=timezone,
                **extra,
            )
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
def unavailability_factory(tutor_factory):
    """Создаёт отметку недоступности и возвращает её id.

    `tutor_id` по умолчанию — у свежесозданного репетитора; значения по
    умолчанию валидны для обоих режимов: `period` — отпуск 26.10–30.10.2026,
    `weekday` — суббота без ограничения срока.
    """

    def _create(
        tutor_id: str | None = None,
        mode: str = "period",
        **extra,
    ):
        from datetime import date

        from app.database import SessionLocal
        from app.unavailability.models.unavailability import TutorUnavailability

        if tutor_id is None:
            tutor_id = tutor_factory()

        if mode == "weekday":
            values = {
                "mode": "weekday",
                "reason": "dayoff",
                "weekday": 5,
            }
        else:
            values = {
                "mode": "period",
                "reason": "vacation",
                "start_date": date(2026, 10, 26),
                "end_date": date(2026, 10, 30),
            }
        values.update(extra)

        with SessionLocal() as session:
            mark = TutorUnavailability(tutor_id=tutor_id, **values)
            session.add(mark)
            session.commit()
            return mark.id

    return _create


@pytest.fixture()
def lesson_factory(tutor_factory, student_factory, group_factory):
    """Создаёт урок в тестовой БД и возвращает его id.

    По умолчанию — проведённый индивидуальный урок с оплатой 1200 у
    свежесозданного ученика: именно такой урок создаёт списание в счёте.
    Цель (`student_id` или `group_id`) можно передать явно; при передаче
    `group_id` урок становится групповым.
    """

    def _create(
        student_id: str | None = None,
        group_id: str | None = None,
        price: int | None = 1200,
        status: str = "completed",
        **extra,
    ):
        from datetime import UTC, datetime

        from app.database import SessionLocal
        from app.lesson.models.lesson import Lesson

        if student_id is None and group_id is None:
            student_id = student_factory()

        values = {
            "student_id": student_id,
            "group_id": group_id,
            "type": "group" if group_id else "individual",
            "starts_at": datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            "duration_min": 60,
            "price": price,
            "status": status,
        }
        values.update(extra)

        with SessionLocal() as session:
            lesson = Lesson(**values)
            session.add(lesson)
            session.commit()
            return lesson.id

    return _create


@pytest.fixture()
def operation_factory(student_factory):
    """Создаёт операцию счёта и возвращает её id.

    По умолчанию — оплаченный платёж 2000 переводом у свежесозданного
    ученика. `student_id` передаётся явно, когда операция должна попасть
    в счёт конкретного ученика (и репетитора вместе с ним).
    """

    def _create(
        student_id: str | None = None,
        kind: str = "payment",
        amount: int = 2000,
        status: str | None = "paid",
        method: str | None = "transfer",
        **extra,
    ):
        from datetime import UTC, datetime

        from app.database import SessionLocal
        from app.finance.models.account_operation import AccountOperation

        if student_id is None:
            student_id = student_factory()

        values = {
            "student_id": student_id,
            "kind": kind,
            "amount": amount,
            "occurred_at": datetime(2026, 10, 22, 1, 31, tzinfo=UTC),
            # Статус и способ — только у платежа (инвариант БД).
            "status": status if kind == "payment" else None,
            "method": method if kind == "payment" else None,
        }
        values.update(extra)

        with SessionLocal() as session:
            operation = AccountOperation(**values)
            session.add(operation)
            session.commit()
            return operation.id

    return _create


@pytest.fixture()
def expect_integrity_error():
    """Контекст: `session.commit()` обязан упасть с IntegrityError.

    Проверки CHECK-ограничений и частичных индексов: запись с недопустимым
    значением не должна сохраниться, даже если её кладут в обход сервисов.
    Откат обязателен — иначе упавшая транзакция отравит общий коннект.
    """
    from contextlib import contextmanager

    from sqlalchemy.exc import IntegrityError

    from app.database import SessionLocal

    @contextmanager
    def _expect():
        with SessionLocal() as session:
            yield session
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return
        raise AssertionError("ожидался IntegrityError, но запись сохранилась")

    return _expect


@pytest.fixture()
def slot_factory(tutor_factory):
    """Создаёт окно для записи и возвращает его id.

    По умолчанию — публичное окно на 40 минут в будущем (14.10.2027 14:00 UTC),
    чтобы состояние окна не зависело от даты прогона. `starts_at` можно
    передать позиционно вторым аргументом — так же, как в локальных
    хелперах, которые эта фабрика заменила.
    """

    def _create(tutor_id: str | None = None, starts_at=None, duration_min: int = 40, **extra):
        from datetime import UTC, datetime

        from app.database import SessionLocal
        from app.slot.models.slot import Slot

        if tutor_id is None:
            tutor_id = tutor_factory()
        if starts_at is None:
            starts_at = datetime(2027, 10, 14, 14, 0, tzinfo=UTC)

        with SessionLocal() as session:
            slot = Slot(
                tutor_id=tutor_id,
                starts_at=starts_at,
                duration_min=duration_min,
                **extra,
            )
            session.add(slot)
            session.commit()
            return slot.id

    return _create


@pytest.fixture()
def booking_factory():
    """Создаёт бронь окна и возвращает её id.

    По умолчанию — заявка «Ожидает подтверждения» с заполненными именем и
    контактом: такие данные нужны и для подтверждения, и для проверки
    разметки карточки.
    """

    def _create(slot_id: str, status: str = "pending", **extra):
        from app.booking.models.booking import Booking
        from app.database import SessionLocal

        with SessionLocal() as session:
            booking = Booking(
                slot_id=slot_id,
                name=extra.pop("name", "Мария Петрова"),
                contact=extra.pop("contact", "+7 999 000-00-00"),
                status=status,
                **extra,
            )
            session.add(booking)
            session.commit()
            return booking.id

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
