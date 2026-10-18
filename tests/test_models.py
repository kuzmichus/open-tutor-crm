"""Тесты ORM-моделей (Student, Contact, StudentContact, Tutor) и ссылочной целостности."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.student.models.contact import Contact
from app.student.models.student import Student
from app.student.models.student_contact import StudentContact
from app.tutor.models.tutor import Tutor
from app.tutor.models.tutor_session import TutorSession


# --------------------------------------------------------------------------
# Ссылочная целостность
# --------------------------------------------------------------------------
def test_sqlite_foreign_keys_pragma_is_enabled():
    """`PRAGMA foreign_keys` включена на каждом соединении (слушатель connect)."""
    with SessionLocal() as session:
        assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_insert_with_missing_foreign_key_is_rejected():
    """Строка с несуществующим FK отклоняется на уровне БД.

    Регрессия: без слушателя `connect` в `app/database.py` SQLite молча
    принимает такую строку, и в базе появляются сироты.
    """
    with SessionLocal() as session:
        session.add(
            TutorSession(
                tutor_id="00000000-0000-4000-8000-000000000000",
                token="fk-test-token",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("FK на несуществующего репетитора должен был упасть")


# --------------------------------------------------------------------------
# Ученик
# --------------------------------------------------------------------------
def test_create_and_read_student(student_factory):
    """Минимальная карточка: имя + признак ребёнок, остальное пусто."""
    student_id = student_factory(first_name="Иван", kind="child")

    with SessionLocal() as session:
        student = session.get(Student, student_id)
        assert student.first_name == "Иван"
        assert student.kind == "child"
        assert student.status == "new"
        assert student.last_name is None
        assert student.email is None
        assert student.phone is None
        assert student.grade is None
        assert student.school is None
        assert student.level is None
        assert student.notes is None
        assert student.timezone is None
        assert student.payer_contact_id is None
        assert student.remind_lesson is False
        assert student.remind_homework is False
        assert student.remind_cancel is False
        assert isinstance(student.created_at, datetime)
        assert isinstance(student.updated_at, datetime)
        # id — строка uuid4, а не автоинкремент.
        assert isinstance(student.id, str) and len(student.id) == 36


def test_student_ids_are_distinct_uuid4(student_factory):
    """Два ученика получают разные uuid4-идентификаторы."""
    from uuid import UUID

    first_id = student_factory()
    second_id = student_factory()

    assert first_id != second_id
    assert UUID(first_id).version == 4
    assert UUID(second_id).version == 4


def test_full_card_values_are_preserved(tutor_factory, student_factory):
    """Все поля карточки читаются без искажений."""
    tutor_id = tutor_factory()
    student_id = student_factory(
        tutor_id=tutor_id,
        first_name="Мария",
        last_name="Петрова",
        phone="+7 555 555-55-55",
        email="Maria@Example.com",
        kind="child",
        grade=5,
        school="Гимназия №1",
        level="B1",
        notes="Любит задачи со звёздочкой",
        timezone="Europe/Moscow",
        remind_lesson=True,
        remind_cancel=True,
    )

    with SessionLocal() as session:
        student = session.get(Student, student_id)
        assert student.last_name == "Петрова"
        assert student.phone == "+7 555 555-55-55"
        assert student.email == "Maria@Example.com"
        assert student.grade == 5
        assert student.school == "Гимназия №1"
        assert student.level == "B1"
        assert student.notes == "Любит задачи со звёздочкой"
        assert student.timezone == "Europe/Moscow"
        assert student.remind_lesson is True
        assert student.remind_homework is False
        assert student.remind_cancel is True


def test_student_requires_tutor(student_factory):
    """Ученик без репетитора не сохраняется."""
    with SessionLocal() as session:
        session.add(Student(first_name="Безвластный", kind="child"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("Ученик без tutor_id должен был упасть на NOT NULL")


def test_student_email_is_optional_and_not_unique(student_factory):
    """Email необязателен, а совпадение email у двух учеников допустимо."""
    first_id = student_factory(email=None)
    second_id = student_factory(email="dup@example.com")
    third_id = student_factory(email="dup@example.com")

    with SessionLocal() as session:
        assert session.get(Student, first_id).email is None
        duplicates = session.scalars(
            select(Student).where(Student.email == "dup@example.com")
        ).all()
        assert {s.id for s in duplicates} == {second_id, third_id}


def test_student_phone_is_not_unique(student_factory):
    """Одинаковый телефон у разных учеников сохраняется без ошибки."""
    first_id = student_factory(phone="+7 555 000-00-00")
    second_id = student_factory(phone="+7 555 000-00-00")

    with SessionLocal() as session:
        assert session.get(Student, first_id).phone == "+7 555 000-00-00"
        assert session.get(Student, second_id).phone == "+7 555 000-00-00"


def test_student_kind_rejects_unknown_value(student_factory):
    """Признак вне `child`/`adult` отклоняется CHECK-ограничением."""
    with SessionLocal() as session:
        student = Student(tutor_id="ignored", first_name="Странный", kind="teen")
        # tutor_id намеренно невалиден — проверку kind ловим отдельно.
        session.add(student)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("kind='teen' должен был упасть на CHECK")


def test_student_kind_check_is_not_masked_by_foreign_key(tutor_factory, student_factory):
    """`kind` вне значений отклоняется и при валидном репетиторе."""
    tutor_id = tutor_factory()
    with SessionLocal() as session:
        session.add(Student(tutor_id=tutor_id, first_name="Странный", kind="teen"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("kind='teen' должен был упасть на CHECK")


def test_student_grade_out_of_range_is_rejected(tutor_factory, student_factory):
    """Класс 0 и 12 отклоняются CHECK-ограничением."""
    tutor_id = tutor_factory()
    for grade in (0, 12):
        with SessionLocal() as session:
            session.add(
                Student(
                    tutor_id=tutor_id,
                    first_name="Классный",
                    kind="child",
                    grade=grade,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
            else:
                raise AssertionError(f"grade={grade} должен был упасть на CHECK")


def test_student_status_defaults_to_new(student_factory):
    """Статус по умолчанию — «новый»."""
    student_id = student_factory()

    with SessionLocal() as session:
        assert session.get(Student, student_id).status == "new"


def test_student_status_rejects_unknown_value(tutor_factory, student_factory):
    """Статус вне new/active/archived отклоняется CHECK-ограничением."""
    tutor_id = tutor_factory()
    with SessionLocal() as session:
        session.add(
            Student(tutor_id=tutor_id, first_name="Удалённый", kind="child", status="deleted")
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("status='deleted' должен был упасть на CHECK")


# --------------------------------------------------------------------------
# Контакты и привязки
# --------------------------------------------------------------------------
def test_contact_can_exist_without_phone(tutor_factory, student_factory, contact_factory):
    """Контакт создаётся только с ФИО и привязывается к ученику."""
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id, full_name="Мама Ирины")
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        contact = session.get(Contact, contact_id)
        assert contact.full_name == "Мама Ирины"
        assert contact.phone is None
        assert contact.email is None
        assert contact.timezone is None

        session.add(
            StudentContact(student_id=student_id, contact_id=contact_id, relation="мама")
        )
        session.commit()

        link = session.scalars(
            select(StudentContact).where(StudentContact.student_id == student_id)
        ).one()
        assert link.contact_id == contact_id
        assert link.relation == "мама"


def test_contact_requires_tutor():
    """Контакт без репетитора не сохраняется."""
    with SessionLocal() as session:
        session.add(Contact(full_name="Безымянный взрослый"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("Контакт без tutor_id должен был упасть на NOT NULL")


def test_student_contact_pair_is_unique(tutor_factory, student_factory, contact_factory):
    """Повторная привязка того же контакта к тому же ученику запрещена."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    contact_id = contact_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        session.add(StudentContact(student_id=student_id, contact_id=contact_id))
        session.commit()

    with SessionLocal() as session:
        session.add(StudentContact(student_id=student_id, contact_id=contact_id))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("Повторная привязка должна была упасть на UNIQUE")


def test_contact_shared_between_two_students(tutor_factory, student_factory, contact_factory):
    """Один контакт привязывается к двум ученикам без копирования."""
    tutor_id = tutor_factory()
    first_id = student_factory(tutor_id=tutor_id)
    second_id = student_factory(tutor_id=tutor_id)
    contact_id = contact_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        session.add_all(
            [
                StudentContact(student_id=first_id, contact_id=contact_id, relation="мама"),
                StudentContact(student_id=second_id, contact_id=contact_id, relation="мама"),
            ]
        )
        session.commit()

        links = session.scalars(
            select(StudentContact).where(StudentContact.contact_id == contact_id)
        ).all()
        assert {link.student_id for link in links} == {first_id, second_id}


def test_deleting_student_cascades_its_links(tutor_factory, student_factory, contact_factory):
    """Удаление ученика убирает его привязки, но не сами контакты."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    contact_id = contact_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        session.add(StudentContact(student_id=student_id, contact_id=contact_id))
        session.commit()

    with SessionLocal() as session:
        session.execute(delete(Student).where(Student.id == student_id))
        session.commit()

        assert session.scalars(select(StudentContact)).all() == []
        assert session.get(Contact, contact_id) is not None


def test_deleting_contact_cascades_links_and_nulls_payer(
    tutor_factory, student_factory, contact_factory
):
    """Удаление контакта убирает привязки и обнуляет плательщика.

    NULL означает «платит сам ученик» — битой ссылки остаться не должно.
    """
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    contact_id = contact_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        session.add(StudentContact(student_id=student_id, contact_id=contact_id))
        student = session.get(Student, student_id)
        student.payer_contact_id = contact_id
        session.commit()

    with SessionLocal() as session:
        session.execute(delete(Contact).where(Contact.id == contact_id))
        session.commit()

        assert session.scalars(select(StudentContact)).all() == []
        assert session.get(Student, student_id).payer_contact_id is None


def test_deleting_tutor_cascades_students_and_contacts(tutor_factory, student_factory, contact_factory):
    """Удаление репетитора уносит его учеников и контакты."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    contact_id = contact_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        session.add(StudentContact(student_id=student_id, contact_id=contact_id))
        session.commit()

    with SessionLocal() as session:
        session.execute(delete(Tutor).where(Tutor.id == tutor_id))
        session.commit()

        assert session.get(Student, student_id) is None
        assert session.get(Contact, contact_id) is None
        assert session.scalars(select(StudentContact)).all() == []


# --------------------------------------------------------------------------
# Репетитор (существующие тесты)
# --------------------------------------------------------------------------
def test_create_and_read_tutor():
    with SessionLocal() as session:
        tutor = Tutor(name="Мария Сидорова", email="maria@example.com")
        session.add(tutor)
        session.commit()

        fetched = session.query(Tutor).filter_by(email="maria@example.com").one()
        assert fetched.id == tutor.id
        assert fetched.name == "Мария Сидорова"
        assert isinstance(fetched.created_at, datetime)


def test_tutor_email_is_unique():
    with SessionLocal() as session:
        session.add(Tutor(name="Первый", email="dup@example.com"))
        session.commit()

    with SessionLocal() as session:
        session.add(Tutor(name="Второй", email="dup@example.com"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("Дубликат email должен был вызвать IntegrityError")
