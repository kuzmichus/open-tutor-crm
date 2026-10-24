"""Тесты сервисов ученика: форма, контакты, плательщик, сохранение."""

import json

import pytest

from app.database import SessionLocal
from app.student.models.contact import Contact
from app.student.models.student import Student
from app.student.models.student_contact import StudentContact
from app.student.services.contact_lookup import (
    find_contact,
    is_linked,
    lookup_contact,
    normalize_email,
    normalize_phone,
    phone_key,
)
from app.student.services.phone import format_phone
from app.student.services.student_form import (
    parse_contact_rows,
    parse_student_form,
    validate_contacts,
    validate_payer,
)
from app.student.services.student_writer import create_student, update_student
from app.student.services.students import (
    build_cards,
    contact_options,
    contact_options_json,
    list_students,
)

# --------------------------------------------------------------------------
# Разбор формы ученика (5.1)
# --------------------------------------------------------------------------


def _student_data(**overrides) -> dict:
    """Минимальная валидная форма ученика: имя и вид, дальше — по вкусу теста."""
    values = {"first_name": "Маша", "kind": "child"}
    values.update(overrides)
    return values


def test_minimal_form_is_valid():
    data, errors = parse_student_form(_student_data())
    assert errors == []
    assert data["first_name"] == "Маша"
    assert data["kind"] == "child"
    assert data["grade"] is None
    assert data["last_name"] == ""


def test_empty_name_is_rejected():
    _data, errors = parse_student_form(_student_data(first_name="  "))
    assert "Укажите имя ученика." in errors


def test_kind_outside_two_values_is_rejected():
    _data, errors = parse_student_form(_student_data(kind="teen"))
    assert "Выберите, кто ученик: ребёнок или взрослый." in errors


def test_kind_defaults_to_child():
    data, errors = parse_student_form({"first_name": "Маша"})
    assert errors == []
    assert data["kind"] == "child"


def test_valid_grade_is_parsed_as_int():
    data, errors = parse_student_form(_student_data(grade="5"))
    assert errors == []
    assert data["grade"] == 5


def test_grade_zero_and_twelve_are_rejected():
    for raw in ("0", "12"):
        data, errors = parse_student_form(_student_data(grade=raw))
        assert "Класс должен быть числом от 1 до 11." in errors
        assert data["grade"] is None


def test_non_numeric_grade_is_rejected():
    _data, errors = parse_student_form(_student_data(grade="пятый"))
    assert "Класс должен быть числом от 1 до 11." in errors


def test_adult_does_not_keep_grade_and_school():
    """Для взрослого класс и школа не сохраняются, даже если пришли."""
    data, errors = parse_student_form(
        _student_data(
            first_name="Ольга",
            kind="adult",
            grade="5",
            school="Гимназия №1",
        )
    )
    assert errors == []
    assert data["grade"] is None
    assert data["school"] == ""


def test_child_keeps_grade_and_school():
    data, errors = parse_student_form(
        _student_data(grade="5", school="Гимназия №1")
    )
    assert errors == []
    assert data["grade"] == 5
    assert data["school"] == "Гимназия №1"


def test_invalid_email_is_rejected():
    _data, errors = parse_student_form(_student_data(email="не-почта"))
    assert "Укажите корректный email." in errors


def test_reminders_are_parsed_independently():
    data, errors = parse_student_form(
        _student_data(remind_lesson="on", remind_cancel="on")
    )
    assert errors == []
    assert data["remind_lesson"] is True
    assert data["remind_homework"] is False
    assert data["remind_cancel"] is True


# --------------------------------------------------------------------------
# Строки контактов
# --------------------------------------------------------------------------


def test_contact_rows_are_parsed_by_index():
    rows = parse_contact_rows(
        {
            "contact_rows": "2",
            "contact_full_name_0": "Мама Ольга",
            "contact_relation_0": "мама",
            "contact_remind_lesson_0": "on",
            "contact_full_name_1": "Бабушка Нина",
            "contact_relation_1": "бабушка",
        }
    )
    assert [row["full_name"] for row in rows] == ["Мама Ольга", "Бабушка Нина"]
    assert rows[0]["relation"] == "мама"
    assert rows[0]["remind_lesson"] is True
    assert rows[1]["remind_lesson"] is False


def test_empty_contact_row_is_skipped():
    rows = parse_contact_rows({"contact_rows": "1"})
    assert rows == []


def test_contact_phone_is_formatted():
    rows = parse_contact_rows(
        {
            "contact_rows": "1",
            "contact_full_name_0": "Мама Ольга",
            "contact_phone_0": "8 (916) 123-45-67",
        }
    )
    assert rows[0]["phone"] == "+7 916 123-45-67"


def test_contact_without_full_name_is_invalid():
    rows = parse_contact_rows(
        {"contact_rows": "1", "contact_phone_0": "+7 555 000-00-00"}
    )
    assert "У каждого контакта укажите ФИО." in validate_contacts(rows)


def test_contact_with_bad_email_is_invalid():
    rows = parse_contact_rows(
        {
            "contact_rows": "1",
            "contact_full_name_0": "Мама",
            "contact_email_0": "плохо",
        }
    )
    assert any("некорректный email" in message for message in validate_contacts(rows))


# --------------------------------------------------------------------------
# Плательщик (5.3)
# --------------------------------------------------------------------------


def test_payer_must_be_linked():
    assert validate_payer("contact-1", {"contact-1"}) == []
    assert validate_payer("contact-2", {"contact-1"}) == [
        "Плательщиком может быть только контакт, привязанный к ученику."
    ]


def test_empty_payer_means_student_pays_himself():
    assert validate_payer("", set()) == []


def test_create_student_rejects_unlinked_payer(tutor_factory):
    """Сохранение с непривязанным контактом отклоняется, ученик не создан."""
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        student, errors = create_student(
            db,
            tutor_id,
            {
                "first_name": "Маша",
                "last_name": "",
                "phone": "",
                "email": "",
                "kind": "child",
                "grade": None,
                "school": "",
                "level": "",
                "notes": "",
                "timezone": "",
                "remind_lesson": False,
                "remind_homework": False,
                "remind_cancel": False,
                "payer_contact_id": "несуществующий-контакт",
            },
            [],
        )
        assert student is None
        assert errors == ["Плательщиком может быть только контакт, привязанный к ученику."]
        assert db.query(Student).filter_by(tutor_id=tutor_id).count() == 0


def test_create_student_accepts_linked_payer(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        contact = Contact(tutor_id=tutor_id, full_name="Мама Ольга")
        db.add(contact)
        db.commit()

        student, errors = create_student(
            db,
            tutor_id,
            {
                "first_name": "Маша",
                "last_name": "",
                "phone": "",
                "email": "",
                "kind": "child",
                "grade": None,
                "school": "",
                "level": "",
                "notes": "",
                "timezone": "",
                "remind_lesson": False,
                "remind_homework": False,
                "remind_cancel": False,
                "payer_contact_id": contact.id,
            },
            [
                {
                    "contact_id": contact.id,
                    "full_name": "Мама Ольга",
                    "phone": "",
                    "email": "",
                    "relation": "мама",
                    "remind_lesson": True,
                    "remind_homework": False,
                    "remind_cancel": False,
                }
            ],
        )
        assert errors == []
        assert student is not None
        assert student.payer_contact_id == contact.id
        assert db.query(StudentContact).filter_by(student_id=student.id).count() == 1


def test_create_student_assigns_color_from_palette(tutor_factory):
    """Новый ученик получает непустой цвет из палитры (1.3)."""
    from app.common.colors import PALETTE

    tutor_id = tutor_factory()
    with SessionLocal() as db:
        student, errors = create_student(db, tutor_id, _student_data(), [])
        assert errors == []
        assert student.color in PALETTE
        saved = db.get(Student, student.id)
        assert saved.color in PALETTE


def test_update_student_keeps_color(tutor_factory, student_factory):
    """Редактирование полей не меняет назначенный цвет (1.5)."""
    from app.common.colors import PALETTE

    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, color=PALETTE[5])

    with SessionLocal() as db:
        student = db.get(Student, student_id)
        errors = update_student(
            db,
            student,
            tutor_id,
            _student_data(first_name="Мария", last_name="Петрова", phone="+7 999 111-22-33"),
            [],
        )
        assert errors == []
        assert db.get(Student, student_id).color == PALETTE[5]


# --------------------------------------------------------------------------
# Поиск контакта (5.2)
# --------------------------------------------------------------------------


def test_phone_normalization_keeps_digits_only():
    assert normalize_phone("+7 (555) 555-55-55") == "75555555555"
    assert normalize_phone(None) == ""


def test_phone_formats_are_equal_by_key():
    assert phone_key("+7 555 555-55-55") == phone_key("8 555 555 55 55")
    assert phone_key("8 555 555 55 55") == phone_key("555 555 55 55")


def test_email_normalization_ignores_case():
    assert normalize_email("  Maria@Example.COM ") == "maria@example.com"

# --------------------------------------------------------------------------
# Формат телефона
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+7 555 555-55-55", "+7 555 555-55-55"),
        ("8 555 555 55 55", "+7 555 555-55-55"),
        ("+7 (555) 555-55-55", "+7 555 555-55-55"),
        ("+79161234567", "+7 916 123-45-67"),
        ("", ""),
        ("   ", ""),
        (None, ""),
        ("+1 555 123 45 67", "+1 555 123 45 67"),
        ("+44 20 7946 0958", "+44 20 7946 0958"),
        ("+7 916 123-45-67 доб. 12", "+7 916 123-45-67 доб. 12"),
        ("позвонить после 18", "позвонить после 18"),
    ],
    ids=[
        "already-formatted",
        "eight-prefix",
        "parentheses",
        "compact",
        "empty",
        "spaces-only",
        "none",
        "usa",
        "uk",
        "extension",
        "letters",
    ],
)
def test_format_phone(raw, expected):
    """Телефон приводится к одному виду; пустое, чужое и текстовое — без порчи."""
    assert format_phone(raw) == expected

def test_phone_formatting_is_idempotent():
    once = format_phone("8(916)123-45-67")
    assert format_phone(once) == once

def test_form_stores_phone_in_single_format():
    data, errors = parse_student_form(
        {"first_name": "Маша", "kind": "child", "phone": "8 555 555 55 55"}
    )
    assert errors == []
    assert data["phone"] == "+7 555 555-55-55"

# --------------------------------------------------------------------------
# Статус в форме
# --------------------------------------------------------------------------

def test_status_defaults_to_new():
    data, errors = parse_student_form({"first_name": "Маша", "kind": "child"})
    assert errors == []
    assert data["status"] == ""

def test_known_status_is_parsed():
    data, errors = parse_student_form(
        {"first_name": "Маша", "kind": "child", "status": "archived"}
    )
    assert errors == []
    assert data["status"] == "archived"

def test_unknown_status_is_rejected():
    _, errors = parse_student_form(
        {"first_name": "Маша", "kind": "child", "status": "deleted"}
    )
    assert "Выберите корректный статус ученика." in errors

def test_empty_status_does_not_reset_existing_status(tutor_factory):
    """Форма без поля статуса не должна сбрасывать статус при сохранении."""
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        student, _ = create_student(
            db,
            tutor_id,
            {
                "first_name": "Маша",
                "last_name": "",
                "phone": "",
                "email": "",
                "kind": "child",
                "grade": None,
                "school": "",
                "level": "",
                "notes": "",
                "timezone": "",
                "status": "active",
                "remind_lesson": False,
                "remind_homework": False,
                "remind_cancel": False,
                "payer_contact_id": "",
            },
            [],
        )
        assert student.status == "active"

        errors = update_student(
            db,
            student,
            tutor_id,
            {
                "first_name": "Маша",
                "last_name": "Петрова",
                "phone": "",
                "email": "",
                "kind": "child",
                "grade": None,
                "school": "",
                "level": "",
                "notes": "",
                "timezone": "",
                "status": "",
                "remind_lesson": False,
                "remind_homework": False,
                "remind_cancel": False,
                "payer_contact_id": "",
            },
            [],
        )
        assert errors == []
        assert db.get(Student, student.id).status == "active"

def test_status_change_is_saved(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        student, _ = create_student(
            db,
            tutor_id,
            {
                "first_name": "Маша",
                "last_name": "",
                "phone": "",
                "email": "",
                "kind": "child",
                "grade": None,
                "school": "",
                "level": "",
                "notes": "",
                "timezone": "",
                "status": "new",
                "remind_lesson": False,
                "remind_homework": False,
                "remind_cancel": False,
                "payer_contact_id": "",
            },
            [],
        )
        update_student(
            db,
            student,
            tutor_id,
            {
                "first_name": "Маша",
                "last_name": "",
                "phone": "",
                "email": "",
                "kind": "child",
                "grade": None,
                "school": "",
                "level": "",
                "notes": "",
                "timezone": "",
                "status": "active",
                "remind_lesson": False,
                "remind_homework": False,
                "remind_cancel": False,
                "payer_contact_id": "",
            },
            [],
        )
        assert db.get(Student, student.id).status == "active"


def test_find_contact_matches_different_phone_format(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        db.add(Contact(tutor_id=tutor_id, full_name="Мама", phone="+7 555 555-55-55"))
        db.commit()

        found = find_contact(db, tutor_id, phone="8 555 555 55 55")
        assert found is not None
        assert found.full_name == "Мама"


def test_find_contact_matches_email_case_insensitively(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        db.add(Contact(tutor_id=tutor_id, full_name="Папа", email="Papa@Example.com"))
        db.commit()

        found = find_contact(db, tutor_id, email="papa@example.COM")
        assert found is not None


def test_find_contact_does_not_cross_tutors(tutor_factory):
    """Контакт другого репетитора не находится."""
    other_tutor_id = tutor_factory(email="other-lookup@example.com")
    mine_id = tutor_factory(email="mine-lookup@example.com")
    with SessionLocal() as db:
        db.add(Contact(tutor_id=other_tutor_id, full_name="Чужой", phone="+7 999 111-22-33"))
        db.commit()

        assert find_contact(db, mine_id, phone="+7 999 111-22-33") is None


def test_lookup_reports_already_linked(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    with SessionLocal() as db:
        contact = Contact(tutor_id=tutor_id, full_name="Мама", phone="+7 555 111-22-33")
        db.add(contact)
        db.commit()

        assert is_linked(db, student_id, contact.id) is False
        result = lookup_contact(
            db, tutor_id, phone="+7 555 111-22-33", student_id=student_id
        )
        assert result["already_linked"] is False

        db.add(StudentContact(student_id=student_id, contact_id=contact.id))
        db.commit()

        result = lookup_contact(
            db, tutor_id, phone="+7 555 111-22-33", student_id=student_id
        )
        assert result["already_linked"] is True


def test_lookup_returns_none_without_matches(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        assert lookup_contact(db, tutor_id, phone="+7 000 000-00-00") is None
        assert lookup_contact(db, tutor_id, phone="", email="") is None


# --------------------------------------------------------------------------
# Сохранение и выборки
# --------------------------------------------------------------------------


def _student_data(**overrides):
    data = {
        "first_name": "Маша",
        "last_name": "",
        "phone": "",
        "email": "",
        "kind": "child",
        "grade": None,
        "school": "",
        "level": "",
        "notes": "",
        "timezone": "",
        "remind_lesson": False,
        "remind_homework": False,
        "remind_cancel": False,
        "payer_contact_id": "",
    }
    data.update(overrides)
    return data


def test_update_changes_fields_but_not_id_or_tutor(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Маша")

    with SessionLocal() as db:
        student = db.get(Student, student_id)
        errors = update_student(
            db,
            student,
            tutor_id,
            _student_data(first_name="Мария", last_name="Петрова", level="B1"),
            [],
        )
        assert errors == []
        assert student.id == student_id
        assert student.tutor_id == tutor_id
        assert student.last_name == "Петрова"
        assert student.level == "B1"


def test_update_reuses_contact_and_updates_it_for_all_students(
    tutor_factory, student_factory
):
    """Изменение контакта видно у всех учеников, к которым он привязан."""
    tutor_id = tutor_factory()
    first_id = student_factory(tutor_id=tutor_id)
    second_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        contact = Contact(tutor_id=tutor_id, full_name="Мама", phone="+7 555 000-00-00")
        db.add(contact)
        db.commit()
        for student_id in (first_id, second_id):
            db.add(StudentContact(student_id=student_id, contact_id=contact.id))
        db.commit()

        row = {
            "contact_id": contact.id,
            "full_name": "Мама Ольга",
            "phone": "+7 555 111-11-11",
            "email": "",
            "relation": "мама",
            "remind_lesson": False,
            "remind_homework": False,
            "remind_cancel": False,
        }
        first = db.get(Student, first_id)
        errors = update_student(db, first, tutor_id, _student_data(), [row])
        assert errors == []

        refreshed = db.get(Contact, contact.id)
        assert refreshed.phone == "+7 555 111-11-11"
        assert db.query(StudentContact).filter_by(contact_id=contact.id).count() == 2


def test_update_removes_unlisted_contacts(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        contact = Contact(tutor_id=tutor_id, full_name="Мама")
        db.add(contact)
        db.commit()
        db.add(StudentContact(student_id=student_id, contact_id=contact.id))
        db.commit()

        student = db.get(Student, student_id)
        errors = update_student(db, student, tutor_id, _student_data(), [])
        assert errors == []
        assert db.query(StudentContact).filter_by(student_id=student_id).count() == 0
        # Сам контакт остаётся: он может быть привязан к другому ученику.
        assert db.get(Contact, contact.id) is not None


def test_list_students_hides_archived_by_default(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    active_id = student_factory(tutor_id=tutor_id, first_name="Активная")
    archived_id = student_factory(
        tutor_id=tutor_id, first_name="Архивная", status="archived"
    )

    with SessionLocal() as db:
        default = list_students(db, tutor_id)
        assert [student.id for student in default] == [active_id]

        archived = list_students(db, tutor_id, status="archived")
        assert [student.id for student in archived] == [archived_id]


def test_list_students_search_by_name_parts(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_factory(
        tutor_id=tutor_id,
        first_name="Мария",
        last_name="Петрова",
        phone="+7 555 111-22-33",
        email="maria@example.com",
    )
    student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Сидоров")

    with SessionLocal() as db:
        assert len(list_students(db, tutor_id, q="петров")) == 1
        assert len(list_students(db, tutor_id, q="555 111")) == 1
        assert len(list_students(db, tutor_id, q="MARIA@")) == 1
        assert len(list_students(db, tutor_id, q="ИВАН")) == 1
        assert list_students(db, tutor_id, q="нет такого") == []


def test_list_students_combines_search_and_status(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, first_name="Мария", status="active")
    student_factory(tutor_id=tutor_id, first_name="Марина", status="archived")

    with SessionLocal() as db:
        found = list_students(db, tutor_id, q="мари", status="archived")
        assert [student.first_name for student in found] == ["Марина"]
        assert list_students(db, tutor_id, q="мари", status="active")[0].first_name == "Мария"


def test_build_cards_includes_payer_and_contacts(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        mom = Contact(tutor_id=tutor_id, full_name="Мама")
        granny = Contact(tutor_id=tutor_id, full_name="Бабушка")
        db.add_all([mom, granny])
        db.commit()
        db.add_all(
            [
                StudentContact(student_id=student_id, contact_id=mom.id, relation="мама"),
                StudentContact(
                    student_id=student_id, contact_id=granny.id, relation="бабушка"
                ),
            ]
        )
        student = db.get(Student, student_id)
        student.payer_contact_id = mom.id
        db.commit()

        card = build_cards(db, [student])[0]
        assert card["payer"].full_name == "Мама"
        assert [item["link"].relation for item in card["contacts"]] == ["мама", "бабушка"]


def test_build_cards_without_contacts_has_no_payer(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        card = build_cards(db, [db.get(Student, student_id)])[0]
        assert card["contacts"] == []
        assert card["payer"] is None


# --------------------------------------------------------------------------
# Выборка контактов для пикера «Добавить контакт» (8.3)
# --------------------------------------------------------------------------


def test_contact_options_are_sorted_by_name(tutor_factory):
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        db.add_all(
            [
                Contact(tutor_id=tutor_id, full_name="Мама", phone="+7 555 111-22-33"),
                Contact(tutor_id=tutor_id, full_name="Бабушка", email="g@example.com"),
            ]
        )
        db.commit()

        options = contact_options(db, tutor_id)
        # Порядок по ФИО — чтобы список не «прыгал» между отрисовками.
        assert [item["full_name"] for item in options] == ["Бабушка", "Мама"]
        assert options[0]["email"] == "g@example.com"
        assert options[1]["phone"] == "+7 555 111-22-33"


def test_contact_options_skip_linked_and_other_tutors(tutor_factory, student_factory):
    """Привязанный контакт исключается, чужие контакты не попадают."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    other_tutor_id = tutor_factory(email="other-options@example.com")

    with SessionLocal() as db:
        mom = Contact(tutor_id=tutor_id, full_name="Мама")
        granny = Contact(tutor_id=tutor_id, full_name="Бабушка")
        db.add_all([mom, granny])
        db.commit()
        db.add(StudentContact(student_id=student_id, contact_id=mom.id))
        db.add(Contact(tutor_id=other_tutor_id, full_name="Чужой контакт"))
        db.commit()

        assert [
            item["full_name"] for item in contact_options(db, tutor_id, exclude_ids={mom.id})
        ] == ["Бабушка"]
        # Без списка исключений возвращаются все контакты репетитора.
        assert [item["full_name"] for item in contact_options(db, tutor_id, set())] == [
            "Бабушка",
            "Мама",
        ]


def test_contact_options_json_keeps_cyrillic_readable(tutor_factory):
    """JSON для data-атрибута формы: кириллица не юникодится (ensure_ascii=False)."""
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        db.add(Contact(tutor_id=tutor_id, full_name="Мама Ольга"))
        db.commit()

        raw = contact_options_json(db, tutor_id)
        assert "Мама Ольга" in raw
        assert json.loads(raw) == [
            {
                "id": db.query(Contact).one().id,
                "full_name": "Мама Ольга",
                "phone": "",
                "email": "",
            }
        ]
