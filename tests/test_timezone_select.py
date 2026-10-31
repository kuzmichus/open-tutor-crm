"""Тесты селекта часового пояса в форме ученика.

Поле «Часовой пояс» — текстовый ввод со списком вариантов (combobox) на
Alpine: варианты приходят с сервера в `data-options`, а значение поля
уходит в форму как есть, поэтому валидация и сохранение не изменились.
"""

import json
import re
from html import unescape
from pathlib import Path

import pytest

from app.common.services.timezones import timezone_options, timezone_options_json

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
BASE_HTML = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
COMBOBOX_JS = (STATIC_DIR / "combobox.js").read_text(encoding="utf-8")
STYLES = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="tz-owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "tz-owner@example.com", "password": PASSWORD},
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
        "school": "",
        "level": "",
        "notes": "",
        "timezone": "",
        "contact_rows": "0",
        "payer_contact_id": "",
    }
    payload.update(overrides)
    return payload


def _timezone_options_from_html(html: str) -> list[dict]:
    """Достаёт и разбирает справочник часовых зон из разметки формы."""
    match = re.search(r'data-options="([^"]*)"', html)
    assert match, "В форме нет справочника часовых зон (data-options)"
    return json.loads(unescape(match.group(1)))


def _timezone_input_tag(html: str) -> str:
    """Тег input поля «Часовой пояс» целиком."""
    start = html.index('id="student-timezone"')
    begin = html.rindex("<", 0, start)
    return html[begin : html.index(">", start) + 1]


# --------------------------------------------------------------------------
# Справочник зон
# --------------------------------------------------------------------------


def test_options_are_real_iana_timezones():
    values = [value for value, _ in timezone_options()]

    assert "Europe/Moscow" in values
    assert "UTC" in values
    # Системный псевдоним локального пояса — не часовой пояс.
    assert "localtime" not in values
    assert len(values) > 100
    assert len(values) == len(set(values))


def test_options_carry_utc_offset_labels():
    labels = dict(timezone_options())

    assert labels["UTC"] == "UTC+00:00"
    assert re.fullmatch(r"UTC[+-]\d{2}:\d{2}", labels["Europe/Moscow"])


def test_options_sorted_by_offset_then_name():
    def offset(label: str) -> int:
        sign = 1 if label[3] == "+" else -1
        return sign * (int(label[4:6]) * 60 + int(label[7:9]))

    pairs = [(offset(label), name) for name, label in timezone_options()]

    assert [minutes for minutes, _ in pairs] == sorted(minutes for minutes, _ in pairs)
    # При равном смещении порядок alphabetical, а не каша из каталога tzdata.
    by_offset: dict[int, list[str]] = {}
    for minutes, name in pairs:
        by_offset.setdefault(minutes, []).append(name)
    for names in by_offset.values():
        assert names == sorted(names)


def test_options_json_is_a_valid_array():
    data = json.loads(timezone_options_json())

    assert len(data) == len(timezone_options())
    assert {"value": "Europe/Moscow", "label": dict(timezone_options())["Europe/Moscow"]} in data
    assert all(set(item) == {"value", "label"} for item in data)


# --------------------------------------------------------------------------
# Разметка формы
# --------------------------------------------------------------------------


def test_form_timezone_is_combobox_with_options(client, owner):
    html = client.get("/tutor/students/new").text

    assert 'role="combobox"' in html
    assert 'aria-controls="student-timezone-listbox"' in html
    assert 'role="listbox"' in html
    # Поле остаётся текстовым с именем `timezone` — форма собирает его как раньше.
    assert 'name="timezone"' in _timezone_input_tag(html)

    options = _timezone_options_from_html(html)
    assert {"value": "Europe/Moscow", "label": dict(timezone_options())["Europe/Moscow"]} in options


def test_edit_form_preselects_saved_timezone(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша", timezone="Europe/Moscow")

    html = client.get(f"/tutor/students/{student_id}/edit").text

    assert 'value="Europe/Moscow"' in _timezone_input_tag(html)


def test_edit_form_without_timezone_has_empty_value(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")

    html = client.get(f"/tutor/students/{student_id}/edit").text

    assert 'value=""' in _timezone_input_tag(html)


def test_chosen_timezone_is_saved(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")

    response = client.post(
        f"/tutor/students/{student_id}",
        data=_create_payload(timezone="Europe/Berlin"),
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    from app.database import SessionLocal
    from app.student.models.student import Student

    with SessionLocal() as db:
        assert db.get(Student, student_id).timezone == "Europe/Berlin"


# --------------------------------------------------------------------------
# Ассеты: JS-виджет, стили, порядок подключения
# --------------------------------------------------------------------------


def test_combobox_js_is_served(client):
    response = client.get("/static/combobox.js")

    assert response.status_code == 200
    assert "Alpine.data" in response.text
    assert '"combobox"' in response.text


def test_combobox_js_registers_before_alpine_loads():
    """Подписка на `alpine:init` должна быть готова до обхода DOM."""
    assert BASE_HTML.index("combobox.js") < BASE_HTML.index("alpine.min.js")


def test_combobox_js_handles_escape_before_modal():
    """Escape закрывает список, а не модалку: событие не доходит до window."""
    assert "stopPropagation" in COMBOBOX_JS


def test_styles_have_combobox_rules():
    for selector in (
        ".combobox__control",
        ".combobox__list",
        ".combobox__option",
        ".combobox__option--active",
        ".combobox__clear",
        ".combobox__note",
    ):
        assert selector in STYLES, f"В styles.css нет правила {selector}"
