"""Тесты поля «Город» в карточке ученика.

Город — свободный текст: справочника нет, а подсказки в форме собираются
из уже введённых городов других учеников этого репетитора. Поэтому тесты
проверяют две вещи: выборку подсказок (только свои ученики, без дублей,
без города открытой карточки) и сохранение набранного значения как есть.
"""

import json
import re
from html import unescape
from pathlib import Path

import pytest

from app.database import SessionLocal
from app.student.models.student import Student
from app.student.services.cities import city_options, city_options_json

ROOT = Path(__file__).resolve().parent.parent

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="city-owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "city-owner@example.com", "password": PASSWORD},
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
        "birth_date": "",
        "city": "",
        "school": "",
        "level": "",
        "notes": "",
        "timezone": "",
        "contact_rows": "0",
        "payer_contact_id": "",
    }
    payload.update(overrides)
    return payload


def _city_options_from_html(html: str) -> list[dict]:
    """Города из `data-options` блока поля «Город» (не первого на странице)."""
    anchor = html.index('id="student-city"')
    block_start = html.rindex('class="combobox"', 0, anchor)
    block = html[block_start : html.index('class="field"', block_start)]
    match = re.search(r'data-options="([^"]*)"', block)
    assert match, "В форме нет подсказок городов (data-options)"
    return json.loads(unescape(match.group(1)))


# --------------------------------------------------------------------------
# Выборка подсказок
# --------------------------------------------------------------------------


def test_options_are_cities_of_tutor_students(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, city="Москва")
    student_factory(tutor_id=tutor_id, city="Казань")

    with SessionLocal() as db:
        assert city_options(db, tutor_id) == [
            {"value": "Казань", "label": ""},
            {"value": "Москва", "label": ""},
        ]


def test_options_ignore_empty_cities(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id)
    student_factory(tutor_id=tutor_id, city="")

    with SessionLocal() as db:
        assert city_options(db, tutor_id) == []


def test_options_collapse_duplicates_case_insensitively(tutor_factory, student_factory):
    """«Москва» и «москва» — один вариант: остаётся первое написание."""
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, city="Москва")
    student_factory(tutor_id=tutor_id, city="москва")

    with SessionLocal() as db:
        assert city_options(db, tutor_id) == [{"value": "Москва", "label": ""}]


def test_options_are_sorted_case_insensitively(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    for city in ("Тверь", "анапа", "Москва", "Брянск"):
        student_factory(tutor_id=tutor_id, city=city)

    with SessionLocal() as db:
        assert [item["value"] for item in city_options(db, tutor_id)] == [
            "анапа",
            "Брянск",
            "Москва",
            "Тверь",
        ]


def test_options_exclude_current_student(tutor_factory, student_factory):
    """Свой город открытой карточки в подсказки не попадает."""
    tutor_id = tutor_factory()
    own_id = student_factory(tutor_id=tutor_id, city="Москва")
    student_factory(tutor_id=tutor_id, city="Казань")

    with SessionLocal() as db:
        assert city_options(db, tutor_id, exclude_student_id=own_id) == [
            {"value": "Казань", "label": ""}
        ]


def test_options_do_not_leak_other_tutors(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    other_id = tutor_factory(email="city-other@example.com")
    student_factory(tutor_id=other_id, city="Владивосток")

    with SessionLocal() as db:
        assert city_options(db, tutor_id) == []


def test_options_json_keeps_cyrillic_readable(tutor_factory, student_factory):
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, city="Москва")

    with SessionLocal() as db:
        raw = city_options_json(db, tutor_id)
        assert "Москва" in raw
        assert json.loads(raw) == [{"value": "Москва", "label": ""}]


# --------------------------------------------------------------------------
# Разметка формы
# --------------------------------------------------------------------------


def test_form_offers_cities_of_other_students(client, owner, student_factory):
    student_factory(tutor_id=owner, city="Москва")
    student_factory(tutor_id=owner, city="Казань")

    html = client.get("/tutor/students/new").text

    assert [item["value"] for item in _city_options_from_html(html)] == [
        "Казань",
        "Москва",
    ]


def test_edit_form_hides_own_city_from_options(client, owner, student_factory):
    own_id = student_factory(tutor_id=owner, city="Москва")
    student_factory(tutor_id=owner, city="Казань")

    html = client.get(f"/tutor/students/{own_id}/edit").text

    assert [item["value"] for item in _city_options_from_html(html)] == ["Казань"]


# --------------------------------------------------------------------------
# Сохранение
# --------------------------------------------------------------------------


def test_city_is_saved(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")

    response = client.post(
        f"/tutor/students/{student_id}",
        data=_create_payload(city="Москва"),
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.get(Student, student_id).city == "Москва"


def test_city_not_in_options_is_saved_as_typed(client, owner, student_factory):
    """Города нет в подсказках — он всё равно сохраняется как набран."""
    student_factory(tutor_id=owner, city="Москва")
    student_id = student_factory(tutor_id=owner, first_name="Маша")

    client.post(
        f"/tutor/students/{student_id}",
        data=_create_payload(city="Новый Уренгой"),
        headers={"HX-Request": "true"},
    )

    with SessionLocal() as db:
        assert db.get(Student, student_id).city == "Новый Уренгой"


def test_city_is_saved_for_adult(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Ольга", kind="adult")

    client.post(
        f"/tutor/students/{student_id}",
        data=_create_payload(first_name="Ольга", kind="adult", city="Казань", school="Школа"),
        headers={"HX-Request": "true"},
    )

    with SessionLocal() as db:
        student = db.get(Student, student_id)
        assert student.city == "Казань"
        # Школа у взрослого по-прежнему не сохраняется.
        assert student.school is None


def test_empty_city_clears_it(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша", city="Москва")

    client.post(
        f"/tutor/students/{student_id}",
        data=_create_payload(city=""),
        headers={"HX-Request": "true"},
    )

    with SessionLocal() as db:
        assert db.get(Student, student_id).city is None
