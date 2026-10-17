"""Тесты ORM-моделей (Student, Tutor)."""

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.student.models.student import Student
from app.tutor.models.tutor import Tutor


def test_create_and_read_student():
    with SessionLocal() as session:
        student = Student(name="Иван Петров", email="ivan@example.com")
        session.add(student)
        session.commit()

        fetched = session.query(Student).filter_by(email="ivan@example.com").one()
        assert fetched.id == student.id
        assert fetched.name == "Иван Петров"
        assert isinstance(fetched.created_at, datetime)


def test_create_and_read_tutor():
    with SessionLocal() as session:
        tutor = Tutor(name="Мария Сидорова", email="maria@example.com")
        session.add(tutor)
        session.commit()

        fetched = session.query(Tutor).filter_by(email="maria@example.com").one()
        assert fetched.id == tutor.id
        assert fetched.name == "Мария Сидорова"
        assert isinstance(fetched.created_at, datetime)


def test_student_email_is_unique():
    with SessionLocal() as session:
        session.add(Student(name="Первый", email="dup@example.com"))
        session.commit()

    with SessionLocal() as session:
        session.add(Student(name="Второй", email="dup@example.com"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("Дубликат email должен был вызвать IntegrityError")


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
