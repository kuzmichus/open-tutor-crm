"""Тесты страниц доменных модулей (tutor, student)."""


def test_tutors_page_renders(client):
    response = client.get("/tutors")
    assert response.status_code == 200
    assert "Репетиторы" in response.text


def test_students_page_renders(client):
    response = client.get("/students")
    assert response.status_code == 200
    assert "Ученики" in response.text


def test_tutors_page_lists_created_tutor(client):
    from app.database import SessionLocal
    from app.tutor.models.tutor import Tutor

    with SessionLocal() as session:
        session.add(Tutor(name="Тестовый Тьютор", email="list@example.com"))
        session.commit()

    response = client.get("/tutors")
    assert "Тестовый Тьютор" in response.text
