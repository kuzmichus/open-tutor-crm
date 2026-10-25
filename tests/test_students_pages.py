"""Тесты страниц и операций с учениками (список, создание, правка, архив)."""

import pytest

from app.database import SessionLocal
from app.student.models.contact import Contact
from app.student.models.student import Student
from app.student.models.student_contact import StudentContact

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _create_payload(**overrides) -> dict:
    payload = {
        "first_name": "Маша",
        "last_name": "",
        "phone": "",
        "email": "",
        "kind": "child",
        "grade": "",
        "school": "",
        "level": "",
        "notes": "",
        "timezone": "",
        "contact_rows": "0",
        "payer_contact_id": "",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------
# Доступ
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/tutor/students"),
        ("get", "/tutor/students/list"),
        ("get", "/tutor/students/new"),
        ("post", "/tutor/students"),
        ("get", "/tutor/students/contacts/lookup"),
    ],
)
def test_operations_require_login(client, method, url):
    """Без сессии изменения не применяются, а запрос уходит на вход."""
    response = getattr(client, method)(url, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_unknown_student_returns_404(client, owner):
    response = client.get("/tutor/students/нет-такого", follow_redirects=False)
    assert response.status_code == 404


def test_foreign_student_returns_404(client, owner, tutor_factory, student_factory):
    """Чужая карточка — 404, а не 403 и не пустая страница."""
    other_id = tutor_factory(email="other@example.com")
    foreign_student_id = student_factory(tutor_id=other_id, first_name="Чужой")

    response = client.get(f"/tutor/students/{foreign_student_id}", follow_redirects=False)
    assert response.status_code == 404
    assert "Чужой" not in response.text


def test_foreign_student_cannot_be_edited_or_archived(
    client, owner, tutor_factory, student_factory
):
    other_id = tutor_factory(email="other2@example.com")
    foreign_student_id = student_factory(tutor_id=other_id, first_name="Чужой")

    assert client.get(f"/tutor/students/{foreign_student_id}/edit").status_code == 404
    assert client.post(f"/tutor/students/{foreign_student_id}/archive").status_code == 404

    with SessionLocal() as db:
        assert db.get(Student, foreign_student_id).status == "new"


# --------------------------------------------------------------------------
# Список и поиск
# --------------------------------------------------------------------------


def test_list_shows_own_students(client, owner, student_factory):
    student_factory(tutor_id=owner, first_name="Мария", last_name="Петрова")
    response = client.get("/tutor/students")
    assert response.status_code == 200
    assert "Мария" in response.text
    assert "Петрова" in response.text


def test_empty_list_shows_message(client, owner):
    response = client.get("/tutor/students")
    assert "Учеников пока нет" in response.text


def test_search_by_last_name_fragment(client, owner, student_factory):
    student_factory(tutor_id=owner, first_name="Мария", last_name="Петрова")
    student_factory(tutor_id=owner, first_name="Иван", last_name="Сидоров")

    response = client.get("/tutor/students/list", params={"q": "петров"})
    assert "Мария" in response.text
    assert "Иван" not in response.text


def test_status_filter_archived(client, owner, student_factory):
    student_factory(tutor_id=owner, first_name="Активная", status="active")
    student_factory(tutor_id=owner, first_name="Архивная", status="archived")

    default = client.get("/tutor/students/list")
    assert "Активная" in default.text
    assert "Архивная" not in default.text

    archived = client.get("/tutor/students/list", params={"status": "archived"})
    assert "Архивная" in archived.text
    assert "Активная" not in archived.text


def test_search_combined_with_filter(client, owner, student_factory):
    student_factory(tutor_id=owner, first_name="Мария", status="active")
    student_factory(tutor_id=owner, first_name="Марина", status="archived")

    response = client.get("/tutor/students/list", params={"q": "мари", "status": "archived"})
    assert "Марина" in response.text
    assert "Мария" not in response.text


def test_empty_search_result_has_message(client, owner, student_factory):
    student_factory(tutor_id=owner, first_name="Мария")
    response = client.get("/tutor/students/list", params={"q": "нет такого"})
    assert response.status_code == 200
    assert "Ничего не найдено" in response.text


# --------------------------------------------------------------------------
# Создание
# --------------------------------------------------------------------------


def test_create_student_success(client, owner):
    response = client.post(
        "/tutor/students",
        data=_create_payload(first_name="Маша", kind="child", grade="5"),
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "student-saved" in response.headers.get("HX-Trigger", "")
    assert "Маша" in response.text

    with SessionLocal() as db:
        student = db.query(Student).filter_by(tutor_id=owner, first_name="Маша").one()
        assert student.status == "new"
        assert student.grade == 5
        assert student.kind == "child"

    # Созданный ученик виден в списке по умолчанию (не архивный).
    assert "Маша" in client.get("/tutor/students/list").text


def test_create_student_without_htmx_redirects(client, owner):
    response = client.post(
        "/tutor/students",
        data=_create_payload(first_name="Маша"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/students"


def test_create_without_name_shows_error(client, owner):
    response = client.post("/tutor/students", data=_create_payload(first_name=""))
    assert response.status_code == 200
    assert "Укажите имя ученика." in response.text

    with SessionLocal() as db:
        assert db.query(Student).filter_by(tutor_id=owner).count() == 0


def test_create_with_grade_12_shows_error(client, owner):
    response = client.post("/tutor/students", data=_create_payload(grade="12"))
    assert "Класс должен быть числом от 1 до 11." in response.text

    with SessionLocal() as db:
        assert db.query(Student).filter_by(tutor_id=owner).count() == 0


def test_create_ignores_tutor_id_from_form(client, owner, tutor_factory):
    """`tutor_id` берётся из сессии, а не из формы."""
    foreign_id = tutor_factory(email="foreign-tutor@example.com")
    client.post(
        "/tutor/students",
        data=_create_payload(first_name="Маша", tutor_id=foreign_id),
    )

    with SessionLocal() as db:
        student = db.query(Student).filter_by(first_name="Маша").one()
        assert student.tutor_id == owner


def test_create_with_contacts_and_payer(client, owner):
    response = client.post(
        "/tutor/students",
        data=_create_payload(
            first_name="Маша",
            contact_rows="2",
            contact_full_name_0="Мама Ольга",
            contact_relation_0="мама",
            contact_remind_lesson_0="on",
            contact_full_name_1="Бабушка Нина",
            contact_relation_1="бабушка",
            payer_contact_id="",  # заполним после создания контактов
        ),
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        student = db.query(Student).filter_by(first_name="Маша").one()
        links = (
            db.query(StudentContact).filter_by(student_id=student.id).all()
        )
        assert len(links) == 2
        relations = {
            db.get(Contact, link.contact_id).full_name: link.relation for link in links
        }
        assert relations == {"Мама Ольга": "мама", "Бабушка Нина": "бабушка"}


# --------------------------------------------------------------------------
# Редактирование
# --------------------------------------------------------------------------


def test_edit_form_shows_existing_values(client, owner, student_factory):
    student_id = student_factory(
        tutor_id=owner, first_name="Маша", last_name="Петрова", level="B1"
    )
    response = client.get(f"/tutor/students/{student_id}/edit")
    assert response.status_code == 200
    assert "Петрова" in response.text
    assert "B1" in response.text


def test_update_changes_last_name_and_level(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    response = client.post(
        f"/tutor/students/{student_id}",
        data=_create_payload(first_name="Маша", last_name="Петрова", level="B1"),
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Петрова" in response.text

    with SessionLocal() as db:
        student = db.get(Student, student_id)
        assert student.last_name == "Петрова"
        assert student.level == "B1"
        assert student.id == student_id
        assert student.tutor_id == owner


def test_update_changes_payer(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    with SessionLocal() as db:
        mom = Contact(tutor_id=owner, full_name="Мама")
        dad = Contact(tutor_id=owner, full_name="Папа")
        db.add_all([mom, dad])
        db.commit()
        db.add_all(
            [
                StudentContact(student_id=student_id, contact_id=mom.id, relation="мама"),
                StudentContact(student_id=student_id, contact_id=dad.id, relation="папа"),
            ]
        )
        student = db.get(Student, student_id)
        student.payer_contact_id = mom.id
        db.commit()
        mom_id, dad_id = mom.id, dad.id

    client.post(
        f"/tutor/students/{student_id}",
        data=_create_payload(
            first_name="Маша",
            contact_rows="2",
            contact_id_0=mom_id,
            contact_full_name_0="Мама",
            contact_relation_0="мама",
            contact_id_1=dad_id,
            contact_full_name_1="Папа",
            contact_relation_1="папа",
            payer_contact_id=dad_id,
        ),
    )

    with SessionLocal() as db:
        student = db.get(Student, student_id)
        assert student.payer_contact_id == dad_id
        assert (
            db.query(StudentContact).filter_by(student_id=student_id).count() == 2
        )


def test_update_rejects_unlinked_payer(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    with SessionLocal() as db:
        stranger = Contact(tutor_id=owner, full_name="Посторонний")
        db.add(stranger)
        db.commit()
        stranger_id = stranger.id

    response = client.post(
        f"/tutor/students/{student_id}",
        data=_create_payload(first_name="Маша", payer_contact_id=stranger_id),
    )
    assert "Плательщиком может быть только контакт, привязанный к ученику." in response.text

    with SessionLocal() as db:
        assert db.get(Student, student_id).payer_contact_id is None


# --------------------------------------------------------------------------
# Архив
# --------------------------------------------------------------------------


def test_archive_hides_student_from_default_list(client, owner, student_factory):
    """Архив отдаёт обновлённую карточку и просит список перезапроситься."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")

    response = client.post(
        f"/tutor/students/{student_id}/archive",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "chip--archived" in response.text
    assert "student-saved" in response.headers.get("HX-Trigger", "")

    # Перезапрос списка (его делает htmx по событию) убирает карточку.
    assert "Маша" not in client.get("/tutor/students/list").text
    assert "Маша" in client.get("/tutor/students/list", params={"status": "archived"}).text


def test_unarchive_makes_student_active(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша", status="archived")

    client.post(f"/tutor/students/{student_id}/archive", headers={"HX-Request": "true"})

    with SessionLocal() as db:
        assert db.get(Student, student_id).status == "active"
    assert "Маша" in client.get("/tutor/students/list").text


def test_archive_keeps_data_and_contacts(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша", level="B1")
    with SessionLocal() as db:
        contact = Contact(tutor_id=owner, full_name="Мама")
        db.add(contact)
        db.commit()
        db.add(StudentContact(student_id=student_id, contact_id=contact.id))
        db.commit()
        contact_id = contact.id

    client.post(f"/tutor/students/{student_id}/archive", headers={"HX-Request": "true"})

    with SessionLocal() as db:
        assert db.get(Student, student_id).level == "B1"
        assert (
            db.query(StudentContact).filter_by(student_id=student_id).count() == 1
        )
        assert db.get(Contact, contact_id) is not None


# --------------------------------------------------------------------------
# Поиск контакта
# --------------------------------------------------------------------------


def test_lookup_finds_own_contact(client, owner):
    with SessionLocal() as db:
        db.add(Contact(tutor_id=owner, full_name="Мама Ольга", phone="+7 555 111-22-33"))
        db.commit()

    response = client.get(
        "/tutor/students/contacts/lookup", params={"phone": "8 555 111 22 33"}
    )
    assert response.status_code == 200
    assert "Мама Ольга" in response.text
    assert "Использовать" in response.text
    assert "Это другой человек" in response.text


def test_lookup_does_not_find_foreign_contact(client, owner, tutor_factory):
    other_id = tutor_factory(email="lookup-other@example.com")
    with SessionLocal() as db:
        db.add(Contact(tutor_id=other_id, full_name="Чужой", phone="+7 999 000-00-00"))
        db.commit()

    response = client.get(
        "/tutor/students/contacts/lookup", params={"phone": "+7 999 000-00-00"}
    )
    assert "Чужой" not in response.text
    assert "Использовать" not in response.text


def test_lookup_reports_already_linked(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    with SessionLocal() as db:
        contact = Contact(tutor_id=owner, full_name="Мама", phone="+7 555 111-22-33")
        db.add(contact)
        db.commit()
        db.add(StudentContact(student_id=student_id, contact_id=contact.id))
        db.commit()

    response = client.get(
        "/tutor/students/contacts/lookup",
        params={"phone": "+7 555 111-22-33", "student_id": student_id},
    )
    assert "уже добавлен" in response.text
    assert "Использовать" not in response.text


# --------------------------------------------------------------------------
# Карточка
# --------------------------------------------------------------------------


def test_card_page_shows_fields_and_contacts(client, owner, student_factory):
    student_id = student_factory(
        tutor_id=owner,
        first_name="Маша",
        last_name="Петрова",
        kind="child",
        grade=5,
        school="Гимназия №1",
        level="B1",
        timezone="Europe/Moscow",
    )
    with SessionLocal() as db:
        contact = Contact(tutor_id=owner, full_name="Мама Ольга", phone="+7 555 111-22-33")
        db.add(contact)
        db.commit()
        db.add(
            StudentContact(
                student_id=student_id,
                contact_id=contact.id,
                relation="мама",
                remind_lesson=True,
            )
        )
        student = db.get(Student, student_id)
        student.payer_contact_id = contact.id
        db.commit()

    response = client.get(f"/tutor/students/{student_id}")
    assert response.status_code == 200
    for fragment in ("Маша", "Петрова", "Гимназия №1", "B1", "Europe/Moscow", "Мама Ольга", "мама"):
        assert fragment in response.text


def test_card_without_contacts_renders(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Взрослый", kind="adult")
    response = client.get(f"/tutor/students/{student_id}")
    assert response.status_code == 200
    assert "Контакты не добавлены" in response.text


def test_card_requires_login(client, owner, student_factory):
    """Карточка без действующей сессии — редирект на вход."""
    student_id = student_factory(tutor_id=owner)
    client.post("/tutor/logout", follow_redirects=False)

    response = client.get(f"/tutor/students/{student_id}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
