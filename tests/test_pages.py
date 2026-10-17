"""Тесты страниц доменных модулей (tutor, student)."""


def test_students_page_renders(client):
    response = client.get("/students")
    assert response.status_code == 200
    assert "Ученики" in response.text


def test_tutors_list_page_removed(client):
    """Страница списка `/tutors` удалена полностью."""
    response = client.get("/tutors")
    assert response.status_code == 404
