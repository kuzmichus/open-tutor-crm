"""Изоляция учеников и контактов между репетиторами.

Сквозной сценарий: два репетитора, у каждого ученик со своим контактом.
Репетитор A не должен видеть данные репетитора B ни в списке, ни в поиске
контактов, ни по прямому URL — включая попытки изменить чужую запись.

Каждый TestClient держит собственный набор cookie, поэтому две сессии
действительно независимы.
"""

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.student.models.contact import Contact
from app.student.models.student import Student
from app.student.models.student_contact import StudentContact
from main import app

PASSWORD = "Секретный-Пароль-1"

def _login(email: str) -> TestClient:
    """Клиент с собственной сессией указанного репетитора."""
    client = TestClient(app)
    response = client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/"
    return client

@pytest.fixture()
def two_tutors(tutor_factory):
    """Два репетитора, у каждого ученик со своим контактом.

    Возвращает словарь с id и готовыми клиентами (уже вошедшими).
    """
    tutor_a = tutor_factory(email="iso-a@example.com", password=PASSWORD)
    tutor_b = tutor_factory(email="iso-b@example.com", password=PASSWORD)

    with SessionLocal() as db:
        student_a = Student(tutor_id=tutor_a, first_name="Алиса", last_name="Своя")
        student_b = Student(tutor_id=tutor_b, first_name="Борис", last_name="Чужой")
        contact_a = Contact(
            tutor_id=tutor_a, full_name="Мама Алисы", phone="+7 111 111-11-11"
        )
        contact_b = Contact(
            tutor_id=tutor_b, full_name="Мама Бориса", phone="+7 222 222-22-22"
        )
        db.add_all([student_a, student_b, contact_a, contact_b])
        db.flush()
        db.add_all(
            [
                StudentContact(student_id=student_a.id, contact_id=contact_a.id, relation="мама"),
                StudentContact(student_id=student_b.id, contact_id=contact_b.id, relation="мама"),
            ]
        )
        db.commit()

        ids = {
            "tutor_a": tutor_a,
            "tutor_b": tutor_b,
            "student_a": student_a.id,
            "student_b": student_b.id,
            "contact_a": contact_a.id,
            "contact_b": contact_b.id,
        }

    client_a = _login("iso-a@example.com")
    client_b = _login("iso-b@example.com")
    yield {**ids, "client_a": client_a, "client_b": client_b}
    client_a.close()
    client_b.close()

# --------------------------------------------------------------------------
# Список
# --------------------------------------------------------------------------

def test_list_shows_only_own_students(two_tutors):
    html = two_tutors["client_a"].get("/tutor/students").text
    assert "Алиса" in html
    assert "Борис" not in html
    assert "Мама Бориса" not in html

def test_search_does_not_reach_other_tutor(two_tutors):
    """Поиск по фамилии чужого ученика не даёт результата."""
    response = two_tutors["client_a"].get("/tutor/students/list", params={"q": "Чужой"})
    assert response.status_code == 200
    assert "Борис" not in response.text
    assert "Ничего не найдено" in response.text

def test_archived_filter_does_not_leak_other_tutor(two_tutors):
    response = two_tutors["client_a"].get(
        "/tutor/students/list", params={"status": "archived"}
    )
    assert response.status_code == 200
    assert "Борис" not in response.text

# --------------------------------------------------------------------------
# Прямой URL
# --------------------------------------------------------------------------

def test_direct_url_to_foreign_student_is_404(two_tutors):
    response = two_tutors["client_a"].get(
        f"/tutor/students/{two_tutors['student_b']}", follow_redirects=False
    )
    assert response.status_code == 404
    assert "Борис" not in response.text

def test_foreign_student_forms_are_404(two_tutors):
    client = two_tutors["client_a"]
    assert client.get(f"/tutor/students/{two_tutors['student_b']}/edit").status_code == 404
    assert (
        client.post(f"/tutor/students/{two_tutors['student_b']}/archive").status_code == 404
    )

def test_foreign_student_cannot_be_updated(two_tutors):
    client = two_tutors["client_a"]
    response = client.post(
        f"/tutor/students/{two_tutors['student_b']}",
        data={
            "first_name": "Взлом",
            "kind": "child",
            "contact_rows": "0",
        },
    )
    assert response.status_code == 404

    with SessionLocal() as db:
        assert db.get(Student, two_tutors["student_b"]).first_name == "Борис"

# --------------------------------------------------------------------------
# Поиск контактов
# --------------------------------------------------------------------------

def test_lookup_does_not_find_foreign_contact(two_tutors):
    response = two_tutors["client_a"].get(
        "/tutor/students/contacts/lookup", params={"phone": "+7 222 222-22-22"}
    )
    assert response.status_code == 200
    assert "Мама Бориса" not in response.text
    assert "Использовать" not in response.text

def test_lookup_does_not_expose_foreign_student_link(two_tutors):
    """Даже с чужим `student_id` контакт другого репетитора не раскрывается."""
    response = two_tutors["client_a"].get(
        "/tutor/students/contacts/lookup",
        params={
            "phone": "+7 222 222-22-22",
            "student_id": two_tutors["student_b"],
        },
    )
    assert "Мама Бориса" not in response.text

def test_lookup_finds_own_contact(two_tutors):
    response = two_tutors["client_a"].get(
        "/tutor/students/contacts/lookup", params={"phone": "+7 111 111-11-11"}
    )
    assert "Мама Алисы" in response.text
    assert "Использовать" in response.text

# --------------------------------------------------------------------------
# Запись
# --------------------------------------------------------------------------

def test_create_ignores_foreign_tutor_id(two_tutors):
    """Владелец всегда берётся из сессии, а не из формы."""
    two_tutors["client_a"].post(
        "/tutor/students",
        data={
            "first_name": "Новый",
            "kind": "adult",
            "tutor_id": two_tutors["tutor_b"],
            "contact_rows": "0",
        },
    )

    with SessionLocal() as db:
        created = db.query(Student).filter_by(first_name="Новый").one()
        assert created.tutor_id == two_tutors["tutor_a"]

def test_foreign_contact_cannot_be_attached_by_id(two_tutors):
    """Чужой `contact_id` в форме не привязывается: создаётся свой контакт."""
    client = two_tutors["client_a"]
    client.post(
        "/tutor/students",
        data={
            "first_name": "Новый",
            "kind": "child",
            "contact_rows": "1",
            "contact_id_0": two_tutors["contact_b"],
            "contact_full_name_0": "Подставленное имя",
            "contact_relation_0": "мама",
        },
    )

    with SessionLocal() as db:
        student = db.query(Student).filter_by(first_name="Новый").one()
        links = db.query(StudentContact).filter_by(student_id=student.id).all()
        assert len(links) == 1
        # Привязка ведёт на контакт этого же репетитора, а не на чужой.
        assert links[0].contact_id != two_tutors["contact_b"]
        assert db.get(Contact, links[0].contact_id).tutor_id == two_tutors["tutor_a"]

def test_each_tutor_keeps_own_list_after_writes(two_tutors):
    """Запись одного репетитора не меняет список другого."""
    client_a, client_b = two_tutors["client_a"], two_tutors["client_b"]
    client_a.post(
        "/tutor/students",
        data={"first_name": "Алиса-2", "kind": "child", "contact_rows": "0"},
    )

    html_a = client_a.get("/tutor/students").text
    html_b = client_b.get("/tutor/students").text
    assert "Алиса-2" in html_a
    assert "Алиса-2" not in html_b
    assert "Борис" in html_b
