"""Общий виджет выбора человека: поле ученика в группе и контакт в ученике.

Оба поля («Добавить ученика» и «Добавить контакт») рисуются одним макросом
`_person_picker.html` и управляются одной Alpine-фабрикой `createPersonPicker`
(`app/static/picker.js`). Тесты держат три вещи:

- список открывается сразу по клику, не дожидаясь ввода;
- поля действительно общие (разметка и поведение не разъехались);
- доменные правила (кто предлагается, что делает выбор) остались в своих
  модулях.
"""

import re
from pathlib import Path

import pytest

from app.database import SessionLocal
from app.student.models.student import Student

PASSWORD = "Секретный-Пароль-1"

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
BASE_HTML = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
PICKER_JS = (STATIC_DIR / "picker.js").read_text(encoding="utf-8")
GROUPS_JS = (STATIC_DIR / "groups.js").read_text(encoding="utf-8")
STUDENTS_JS = (STATIC_DIR / "students.js").read_text(encoding="utf-8")
PICKER_TEMPLATE = (ROOT / "app" / "templates" / "_person_picker.html").read_text(
    encoding="utf-8"
)

@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="picker@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "picker@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id

def _field_markup(html: str, input_id: str) -> str:
    """Фрагмент поля выбора вместе со списком вариантов."""
    start = html.index(f'id="{input_id}"')
    end = html.index("</ul>", start)
    return html[start:end]

# --------------------------------------------------------------------------
# Список открывается без ожидания ввода
# --------------------------------------------------------------------------

def test_picker_opens_on_click_and_focus():
    """Список открывается кликом и фокусом, а не только началом ввода.

    Регрессия: раньше `openList` показывал список лишь при непустом запросе,
    и по клику на «Добавить ученика» ничего не происходило.
    """
    open_list = re.search(r"openList:\s*function\s*\(\)\s*\{(.*?)\}", PICKER_JS, re.S)
    assert open_list, "в picker.js нет openList"
    assert "this.listOpen = true" in open_list.group(1)
    # Никакого условия по введённому запросу внутри openList.
    assert "query" not in open_list.group(1)

    # Поле открывает список и по клику, и по фокусу.
    assert '@focus="openList()"' in PICKER_TEMPLATE
    assert '@click="openList()"' in PICKER_TEMPLATE

def test_picker_filters_while_typing():
    """Ввод фильтрует уже открытый список (не закрывает его)."""
    on_input = re.search(r"onInput:\s*function\s*\(value\)\s*\{(.*?)\}", PICKER_JS, re.S)
    assert on_input
    body = on_input.group(1)
    assert "this.query = value" in body
    assert "this.listOpen = true" in body

# --------------------------------------------------------------------------
# Поле общее для группы и ученика
# --------------------------------------------------------------------------

def test_base_html_loads_picker_before_page_scripts():
    """`picker.js` идёт до страниценных скриптов: они собирают на нём состояние."""
    assert "/static/picker.js" in BASE_HTML
    picker_pos = BASE_HTML.index("/static/picker.js")
    assert picker_pos < BASE_HTML.index("/static/students.js")
    assert picker_pos < BASE_HTML.index("/static/alpine.min.js")
    # Фабрика — Alpine.data через общий хелпер, а не глобальная функция.
    assert "window.createPersonPicker" in PICKER_JS
    assert "window.mergePersonPicker" in PICKER_JS

def test_picker_js_is_served(client):
    response = client.get("/static/picker.js")
    assert response.status_code == 200
    assert "createPersonPicker" in response.text

def test_both_fields_use_shared_picker_markup(owner, client, student_factory):
    """Группа и ученик рисуют поле одним макросом — разметка совпадает."""
    student_factory(tutor_id=owner, first_name="Мария")

    group_html = client.get("/tutor/groups/new").text
    student_html = client.get("/tutor/students/new").text

    for markup in (group_html, student_html):
        assert 'class="person-picker"' in markup
        assert 'role="combobox"' in markup
        assert 'class="combobox__list"' in markup

    # Список группы и список контакта — одинаковый набор элементов.
    group_field = _field_markup(group_html, "group-member-search")
    contact_field = _field_markup(student_html, "contact-add-input")
    for token in (
        '@focus="openList()"',
        '@click="openList()"',
        '@input="onInput($event.target.value)"',
        '@keydown="onKeydown($event)"',
        'x-show="listOpen"',
        ":aria-expanded=\"listOpen ? 'true' : 'false'\"",
    ):
        assert token in group_field, f"в поле группы нет {token}"
        assert token in contact_field, f"в поле контакта нет {token}"

def test_domain_rules_stay_in_domain_scripts():
    """Общий виджет не знает про учеников и контакты: правила — в доменах."""
    # Комментарии не в счёт: в шапке файла перечислены соседние скрипты.
    code = re.sub(r"/\*.*?\*/", "", PICKER_JS, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
    for domain_word in ("contact", "student", "member", "group"):
        assert domain_word not in code.lower(), (
            f"picker.js не должен знать про «{domain_word}»"
        )
    # Домены собирают виджет поверх общей фабрики.
    assert "window.createPersonPicker(" in GROUPS_JS
    assert "window.createPersonPicker(" in STUDENTS_JS
    assert 'Alpine.data("contactAdd"' in STUDENTS_JS

def test_picker_styles_are_shared():
    """У поля один набор стилей на оба экрана."""
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    assert ".person-picker {" in styles
    # Старые стили отдельного поля контактов убраны — иначе поля разъедутся.
    assert ".contact-add" not in styles

def test_group_picker_still_offers_mini_form_action(owner, client, student_factory):
    """Пункт «Добавить ученика» остаётся в конце списка выбора группы."""
    student_factory(tutor_id=owner, first_name="Мария")
    html = client.get("/tutor/groups/new").text

    field = _field_markup(html, "group-member-search")
    assert "combobox__divider" in field
    assert "combobox__option--action" in field
    assert "Добавить ученика" in field
    assert "openMiniForm()" in field

def test_group_picker_shows_limit_and_empty_student_list(owner, client):
    """Поле группы сохраняет свои подписи: лимит и «нет учеников»."""
    html = client.get("/tutor/groups/new").text
    field = _field_markup(html, "group-member-search")
    assert "Макс: 10 участников" in field
    assert "Ничего не найдено" in field

def test_group_picker_excludes_current_members(owner, client, student_factory):
    """Уже состоящие в группе не предлагаются и в общем виджете."""
    from datetime import UTC, datetime

    from app.group.models.group import Group
    from app.group.models.group_member import GroupMember

    member_id = student_factory(tutor_id=owner, first_name="Мария")
    free_id = student_factory(tutor_id=owner, first_name="Свободный")
    with SessionLocal() as db:
        group = Group(tutor_id=owner, name="A")
        db.add(group)
        db.flush()
        db.add(
            GroupMember(
                group_id=group.id,
                student_id=member_id,
                joined_at=datetime(2026, 10, 14, tzinfo=UTC),
            )
        )
        db.commit()
        group_id = group.id

    html = client.get(f"/tutor/groups/{group_id}/edit").text
    start = html.index("data-options=")
    raw = html[start : html.index(">", start)]
    assert "Свободный" in raw
    assert "Мария" not in raw
    assert free_id in raw

def test_contact_picker_excludes_linked_contacts(client, owner, student_factory):
    """Общий виджет не ломает правило контактов: привязанные не предлагаются."""
    from app.student.models.contact import Contact
    from app.student.models.student_contact import StudentContact

    student_id = student_factory(tutor_id=owner, first_name="Маша")
    with SessionLocal() as db:
        contact = Contact(
            tutor_id=owner, full_name="Мама Ольга", phone="+7 555 111-22-33"
        )
        db.add(contact)
        db.flush()
        db.add(StudentContact(student_id=student_id, contact_id=contact.id))
        db.commit()

    html = client.get(f"/tutor/students/{student_id}/edit").text
    start = html.index("data-options=")
    options = html[start + len('data-options="'):]
    options = options[: options.index('"')]
    assert "Мама Ольга" not in options

def test_picker_escapes_modal_close_and_selects_by_enter():
    """Escape гасится, чтобы не закрыть модалку; Enter выбирает вариант."""
    assert "stopPropagation" in PICKER_JS
    # Enter гасится всегда: иначе он отправил бы форму группы.
    enter_block = PICKER_JS[PICKER_JS.index('if (key === "Enter")') :]
    assert "event.preventDefault()" in enter_block[:400]
