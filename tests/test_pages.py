"""Тесты страниц доменных модулей (tutor, student)."""

PASSWORD = "Секретный-Пароль-1"


def _login(client, email="pages-user@example.com"):
    client.post(
        "/tutor/register",
        data={
            "name": "Страничный",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )
    return client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )


def test_students_page_requires_login(client):
    """`/tutor/students` без сессии — редирект на вход, данные не отдаются."""
    response = client.get("/tutor/students", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_students_page_renders_for_owner(client):
    _login(client)
    response = client.get("/tutor/students")
    assert response.status_code == 200
    assert "Ученики" in response.text


def test_students_page_shows_only_own_students(client, tutor_factory, student_factory):
    """В списке нет учеников другого репетитора."""
    other_tutor_id = tutor_factory(name="Чужой", email="other@example.com")
    student_factory(tutor_id=other_tutor_id, first_name="Чужойученик")

    _login(client)
    response = client.get("/tutor/students")
    assert response.status_code == 200
    assert "Чужойученик" not in response.text


def test_tutors_list_page_removed(client):
    """Страница списка `/tutors` удалена полностью."""
    response = client.get("/tutors")
    assert response.status_code == 404
