"""Тесты модальной формы и Alpine-поведения страницы учеников.

Покрывают задачи 8.1–8.5: подключение Alpine локальным файлом, одноэкранную
форму с секциями, блок контактов с аккордеоном строк и поиском существующих,
связку модалки с htmx и переключатель вид-сетка/список с сохранением выбора.
"""

import re
from pathlib import Path

import pytest

from app.database import SessionLocal
from app.student.models.contact import Contact
from app.student.models.student import Student
from app.student.models.student_contact import StudentContact

PASSWORD = "Секретный-Пароль-1"

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
STYLES = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
BASE_HTML = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
STUDENTS_JS = (STATIC_DIR / "students.js").read_text(encoding="utf-8")

@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="modal-owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "modal-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id

# --------------------------------------------------------------------------
# 8.1 Alpine локальным файлом
# --------------------------------------------------------------------------

def test_base_html_loads_local_alpine_with_defer():
    assert '/static/alpine.min.js' in BASE_HTML
    assert re.search(r'<script src="/static/alpine\.min\.js"\s+defer>', BASE_HTML)
    # Никакого CDN: скрипты подключаются только с локального /static.
    script_sources = re.findall(r'<script[^>]*\ssrc="([^"]+)"', BASE_HTML)
    assert script_sources
    assert all(src.startswith("/static/") for src in script_sources), script_sources

def test_alpine_factories_are_loaded_before_alpine():
    """`students.js` подключается до Alpine, иначе `alpine:init` пропущен."""
    assert '/static/students.js' in BASE_HTML
    js_pos = BASE_HTML.index("/static/students.js")
    alpine_pos = BASE_HTML.index("/static/alpine.min.js")
    assert js_pos < alpine_pos
    # Фабрики регистрируются через Alpine.data, а не глобальными функциями.
    assert 'Alpine.data("studentsPage"' in STUDENTS_JS
    assert 'Alpine.data("studentForm"' in STUDENTS_JS
    assert 'addEventListener("alpine:init"' in STUDENTS_JS

def test_alpine_asset_is_served(client):
    response = client.get("/static/alpine.min.js")
    assert response.status_code == 200
    assert len(response.content) > 10_000

def test_students_js_is_served(client):
    response = client.get("/static/students.js")
    assert response.status_code == 200
    assert "Alpine.data" in response.text

def test_x_cloak_rule_exists():
    assert "[x-cloak] { display: none !important; }" in STYLES

def test_list_page_has_no_inline_factories(client, owner):
    """Фабрики живут в общем файле: карточка тоже открывает модалку."""
    html = client.get("/tutor/students").text
    assert "function studentForm" not in html
    assert "function studentsPage" not in html

# --------------------------------------------------------------------------
# 8.2 Форма: секции, подтип, модалка
# --------------------------------------------------------------------------

def test_form_has_all_card_fields(client, owner):
    html = client.get("/tutor/students/new").text
    for name in (
        "first_name",
        "last_name",
        "phone",
        "email",
        "kind",
        "status",
        "grade",
        "school",
        "level",
        "notes",
        "timezone",
        "remind_lesson",
        "remind_homework",
        "remind_cancel",
        "payer_contact_id",
    ):
        assert f'name="{name}"' in html, f"В форме нет поля {name}"

def test_status_select_follows_kind_and_precedes_name(client, owner):
    """Статус — справа от «Кто ученик», имя и фамилия — следующей строкой."""
    html = client.get("/tutor/students/new").text

    kind_pos = html.index('id="kind-label"')
    status_pos = html.index('id="student-status"')
    first_name_pos = html.index('id="student-first-name"')

    assert kind_pos < status_pos < first_name_pos
    # Статус — отдельное поле в том же ряду сетки, а не внутри сегмента.
    status_field = html.rindex('class="field"', 0, status_pos)
    assert status_field > html.index('aria-labelledby="kind-label"')

def test_status_select_has_all_statuses_and_defaults_to_new(client, owner):
    html = client.get("/tutor/students/new").text
    block = html[html.index('id="student-status"') : html.index("</select>", html.index('id="student-status"'))]

    for value in ("new", "active", "archived"):
        assert f'value="{value}"' in block
    # По умолчанию выбран «Новый».
    assert re.search(r'value="new"\s+selected', block)

def test_edit_form_preselects_saved_status(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша", status="active")
    html = client.get(f"/tutor/students/{student_id}/edit").text
    block = html[html.index('id="student-status"') : html.index("</select>", html.index('id="student-status"'))]
    assert re.search(r'value="active"\s+selected', block)

def test_phone_field_has_mask(client, owner):
    html = client.get("/tutor/students/new").text
    phone_input = html[html.index('id="student-phone"') : html.index(">", html.index('id="student-phone"'))]
    assert "data-phone-mask" in phone_input
    assert "+7 555 555-55-55" in phone_input
    assert 'inputmode="tel"' in phone_input

def test_contact_phone_fields_have_mask(client, owner):
    html = client.get("/tutor/students/new").text
    for match in re.finditer(r'id="contact-phone-[^"]+"', html):
        tag_start = html.rindex("<input", 0, match.start())
        tag_end = html.index(">", match.end())
        assert "data-phone-mask" in html[tag_start:tag_end]

def test_students_js_formats_phone_on_input():
    """Форматирование телефона — делегированный обработчик по data-phone-mask."""
    assert "formatPhoneValue" in STUDENTS_JS
    assert 'matches("[data-phone-mask]")' in STUDENTS_JS
    assert 'addEventListener("input"' in STUDENTS_JS
    # Формат совпадает с серверным: +7 555 555-55-55.
    assert 'result = "+7"' in STUDENTS_JS

def test_grid_refreshes_after_save(client, owner):
    """Смена статуса на «В архиве» должна убирать карточку из списка."""
    html = client.get("/tutor/students").text
    grid = html[html.index('id="students-grid"') : html.index("</div>", html.index('id="students-grid"'))]
    assert 'hx-get="/tutor/students/list"' in grid
    assert 'hx-trigger="student-saved from:body"' in grid
    assert 'hx-include="#students-filters"' in grid

def test_form_has_tabs_and_sections(client, owner):
    """Вкладки «Общее/Платежи/Настройки»: секции лежат в панелях вкладок."""
    html = client.get("/tutor/students/new").text
    assert 'role="tablist"' in html
    for tab_id, label in (
        ("student-tab-general", "Общее"),
        ("student-tab-payments", "Платежи"),
        ("student-tab-settings", "Настройки"),
    ):
        assert f'id="{tab_id}"' in html
        assert f'aria-controls="{tab_id.replace("tab-", "panel-")}"' in html
        assert re.search(rf'{tab_id}"[^>]*>\s*{label}\s*</button>', html, re.S)
    # «Платежи» — заглушка: текст о будущих счетах и оплатах.
    assert "появятся здесь позже" in html
    # Секции остались: общее, контакты, плательщик и напоминания.
    assert "Контакты" in html
    assert "Плательщик" in html
    assert "Напоминания" in html
    assert html.count('class="form-section"') >= 4
    # Панели скрываются через x-show: поля всех вкладок уходят в POST.
    for panel in ("general", "payments", "settings"):
        assert f'x-show="tab === \'{panel}\'"' in html
        assert f'data-tab-panel="{panel}"' in html


def test_settings_tab_holds_reminders(client, owner):
    """Настройки уведомлений переехали на вкладку «Настройки»."""
    html = client.get("/tutor/students/new").text
    start = html.index('data-tab-panel="settings"')
    panel = html[start : html.index("</div>", start)]
    for name in ("remind_lesson", "remind_homework", "remind_cancel"):
        assert f'name="{name}"' in panel


def test_modal_actions_are_outside_scrolled_body(client, owner):
    """«Отмена» и «Сохранить» — в футере: видны без прокрутки контента."""
    html = client.get("/tutor/students/new").text
    body_start = html.index('class="modal-body"')
    actions_start = html.index('class="modal-actions"')
    # Футер идёт после тела и не входит в скроллящуюся область.
    assert actions_start > body_start
    assert "Отмена" in html[actions_start:]
    assert 'type="submit"' in html[actions_start:]
    # Тело скроллится, футер прижат к низу модалки.
    assert ".modal-body {" in STYLES
    assert ".modal-actions {" in STYLES
    modal_body = STYLES[STYLES.index(".modal-body {") :]
    assert "overflow-y: auto" in modal_body[: modal_body.index("}")]
    modal_actions = STYLES[STYLES.index(".modal-actions {") :]
    assert "flex-shrink: 0" in modal_actions[: modal_actions.index("}")]


def test_submit_switches_tab_to_invalid_field():
    """Браузер не подсветит поле в скрытой вкладке — Alpine переключает её."""
    assert "revealInvalidField" in STUDENTS_JS
    assert 'querySelector(":invalid")' in STUDENTS_JS
    assert "closest(\"[data-tab-panel]\")" in STUDENTS_JS
    assert 'tab: "general"' in STUDENTS_JS


def test_grade_and_school_depend_on_kind(client, owner):
    html = client.get("/tutor/students/new").text
    grade_field = re.search(r'<div[^>]*data-depends-on-kind="child"[^>]*>.*?student-grade', html, re.S)
    school_field = re.search(r'<div[^>]*data-depends-on-kind="child"[^>]*>.*?student-school', html, re.S)
    assert grade_field, "Поле класса не помечено зависимым от kind"
    assert school_field, "Поле школы не помечено зависимым от kind"
    assert "x-show=\"kind === 'child'\"" in html

def test_modal_uses_alpine_and_closes_by_escape(client, owner):
    html = client.get("/tutor/students/new").text
    assert "x-data=\"studentForm(" in html
    assert "x-show=\"open\"" in html
    assert "x-cloak" in html
    assert '@keydown.escape.window="close()"' in html

# --------------------------------------------------------------------------
# 8.3 Контакты: аккордеон строк, поле добавления с поиском
# --------------------------------------------------------------------------

def test_contact_block_has_lazy_lookup(client, owner):
    """Ленивый дубль-поиск в полях строки: телефон/почта ищут контакт."""
    html = client.get("/tutor/students/new").text
    assert 'hx-get="/tutor/students/contacts/lookup"' in html
    # Задержка обязательна: иначе запрос уходит на каждый символ.
    assert re.search(r'hx-trigger="input changed delay:\d+ms', html)
    assert 'hx-include="closest .contact-row"' in html

def test_linked_contacts_render_as_collapsed_rows(client, owner, student_factory):
    """Привязанный контакт — строка-аккордеон: ФИО, роль, телефон и стрелка."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    with SessionLocal() as db:
        contact = Contact(
            tutor_id=owner, full_name="Мама Ольга", phone="+7 555 111-22-33"
        )
        db.add(contact)
        db.flush()
        db.add(StudentContact(student_id=student_id, contact_id=contact.id, relation="мама"))
        db.commit()

    html = client.get(f"/tutor/students/{student_id}/edit").text

    start = html.index("data-contact-row")
    row = html[start : html.index("</li>", start)]
    # Строка свёрнута: раскрывается кликом по кнопке-сводке.
    assert 'x-data="{ open: false }"' in row
    assert 'aria-expanded="false"' in row
    assert '@click="open = !open"' in row
    # Сводка вместо полей: ФИО, роль и телефон видны сразу.
    assert 'data-summary="full_name"' in row
    assert 'data-summary="relation"' in row
    assert 'data-summary="phone"' in row
    assert "Мама Ольга" in row
    assert "мама" in row
    assert "+7 555 111-22-33" in row
    # Стрелка lucide поворачивается CSS-классом обёртки, а не перерисовывается.
    assert "chevron-right" in row
    assert "contact-row__arrow" in row
    # Форма редактирования внутри строки скрыта до раскрытия.
    assert 'x-show="open"' in row
    assert 'name="contact_full_name_0"' in row
    assert 'name="contact_relation_0"' in row
    assert 'name="contact_remind_lesson_0"' in row

def test_contact_block_starts_empty_with_picker(client, owner):
    """Пустая форма: заглушка вместо пустых строк и поле добавления с поиском."""
    html = client.get("/tutor/students/new").text

    assert 'name="contact_rows" value="0"' in html
    assert "contact-rows__empty" in html

    start = html.index('x-data="contactAdd()"')
    picker = html[start : html.index("</div>", start)]
    assert 'id="contact-add-input"' in picker
    # Варианты — клиентский JSON контактов репетитора (как часовые зоны).
    assert 'data-options="' in picker
    assert '@input="onInput($event.target.value)"' in picker
    assert '@keydown="onKeydown($event)"' in picker
    assert 'aria-controls="contact-add-list"' in picker

def test_contact_picker_offers_existing_contacts(client, owner):
    with SessionLocal() as db:
        db.add(Contact(tutor_id=owner, full_name="Мама Ольга", phone="+7 555 111-22-33"))
        db.commit()

    html = client.get("/tutor/students/new").text
    assert "Мама Ольга" in html

def test_contact_picker_excludes_linked_contacts(client, owner, student_factory):
    """Уже привязанный контакт не предлагается повторно."""
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
    start = html.index('data-options="')
    options = html[start + len('data-options="'):]
    options = options[: options.index('"')]
    assert "Мама Ольга" not in options

def test_contact_rows_are_added_from_template(client, owner):
    """Новая строка берётся из инертного шаблона с очередным индексом."""
    html = client.get("/tutor/students/new").text
    assert 'id="contact-row-template"' in html
    # Индекс в шаблоне — заглушка, которую подставляет JS.
    assert "__index__" in html
    assert "__index__" in STUDENTS_JS
    # Добавляет строку модуль appendContactRow: кнопки «Добавить контакт» нет,
    # контакты добавляются через поле поиска.
    assert "appendContactRow" in STUDENTS_JS
    assert "addRow()" not in html

def test_template_row_is_open_for_new_contact(client, owner):
    """Новая строка раскрывается сразу — заполняют её, а не свёрнутую."""
    html = client.get("/tutor/students/new").text
    start = html.index('id="contact-row-template"')
    template = html[start : html.index("</template>", start)]
    assert 'x-data="{ open: true }"' in template

def test_contact_rows_stay_open_after_validation_error(client, owner):
    """Строки, введённые до ошибки, отрисовываются раскрытыми."""
    response = client.post(
        "/tutor/students",
        data={
            "first_name": "Маша",
            "kind": "child",
            "contact_rows": "1",
            "contact_full_name_0": "",
            "contact_phone_0": "+7 555 555-55-55",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "У каждого контакта укажите ФИО." in response.text

    start = response.text.index("data-contact-row")
    row = response.text[start : response.text.index("</li>", start)]
    assert 'aria-expanded="true"' in row
    assert 'name="contact_phone_0"' in row

def test_students_js_syncs_contact_summary():
    """Строка-сводка (ФИО · роль · телефон) обновляется из полей формы."""
    assert "syncContactSummary" in STUDENTS_JS
    assert "data-summary" in STUDENTS_JS
    # Escape в пикере гасится, чтобы не закрыть модалку целиком.
    assert "stopPropagation" in STUDENTS_JS

def test_suggestion_fragment_has_both_actions(client, owner):
    with SessionLocal() as db:
        db.add(Contact(tutor_id=owner, full_name="Мама Ольга", phone="+7 555 111-22-33"))
        db.commit()

    response = client.get(
        "/tutor/students/contacts/lookup", params={"phone": "+7 555 111-22-33"}
    )
    assert "Использовать" in response.text
    assert "Это другой человек" in response.text
    assert 'data-contact-id=' in response.text

def test_lookup_accepts_row_indexed_form_fields(client, owner):
    """Форма отправляет `contact_phone_0`, а не `phone`."""
    with SessionLocal() as db:
        db.add(Contact(tutor_id=owner, full_name="Мама Ольга", phone="+7 555 111-22-33"))
        db.commit()

    response = client.get(
        "/tutor/students/contacts/lookup",
        params={"contact_phone_0": "+7 555 111-22-33", "row_index": "0"},
    )
    assert "Мама Ольга" in response.text
    assert "Использовать" in response.text

def test_lookup_reports_already_linked_for_form(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    with SessionLocal() as db:
        contact = Contact(tutor_id=owner, full_name="Мама", phone="+7 555 111-22-33")
        db.add(contact)
        db.commit()
        db.add(StudentContact(student_id=student_id, contact_id=contact.id))
        db.commit()

    response = client.get(
        "/tutor/students/contacts/lookup",
        params={
            "contact_phone_0": "+7 555 111-22-33",
            "row_index": "0",
            "student_id": student_id,
        },
    )
    assert "уже добавлен" in response.text
    assert "Использовать" not in response.text

# --------------------------------------------------------------------------
# 8.4 Модалка + htmx
# --------------------------------------------------------------------------

def test_modal_is_opened_into_modal_container(client, owner):
    html = client.get("/tutor/students").text
    assert 'id="modal"' in html
    assert re.search(r'hx-get="/tutor/students/new"\s+hx-target="#modal"', html)

def test_form_saves_into_modal_container(client, owner):
    """Ошибка валидации должна заменять форму, а не сетку."""
    html = client.get("/tutor/students/new").text
    assert re.search(r'hx-post="[^"]+"\s+hx-target="#modal"\s+hx-swap="innerHTML"', html)

def test_successful_create_returns_card_and_closes_modal(client, owner):
    response = client.post(
        "/tutor/students",
        data={
            "first_name": "Маша",
            "kind": "child",
            "contact_rows": "0",
            "payer_contact_id": "",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert 'class="student-card"' in response.text
    assert response.headers["HX-Trigger"] == "student-saved"
    assert response.headers["HX-Retarget"] == "#students-grid"
    assert response.headers["HX-Reswap"] == "afterbegin"
    # Форма закрывается по событию в Alpine-компоненте модалки.
    form_html = client.get("/tutor/students/new").text
    assert '@student-saved.window="close()"' in form_html

def test_validation_error_returns_form_not_card(client, owner):
    response = client.post(
        "/tutor/students",
        data={"first_name": " ", "kind": "child", "contact_rows": "0"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert 'class="student-card"' not in response.text
    assert "Укажите имя ученика." in response.text
    assert "x-data=\"studentForm(" in response.text

def test_update_from_card_page_refreshes_page(client, owner, student_factory):
    """Со страницы карточки сетки в DOM нет — обновляется вся страница."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")

    response = client.post(
        f"/tutor/students/{student_id}",
        data={
            "first_name": "Маша",
            "kind": "child",
            "contact_rows": "0",
            "from_card": "1",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert response.headers["HX-Refresh"] == "true"
    assert "HX-Retarget" not in response.headers

def test_edit_from_card_page_is_marked(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    html = client.get(f"/tutor/students/{student_id}").text
    assert f'hx-get="/tutor/students/{student_id}/edit?from_card=1"' in html

    form = client.get(f"/tutor/students/{student_id}/edit", params={"from_card": "1"}).text
    assert 'name="from_card" value="1"' in form

# --------------------------------------------------------------------------
# 8.5 Переключатель вид-сетка/список
# --------------------------------------------------------------------------

def test_view_toggle_present(client, owner):
    html = client.get("/tutor/students").text
    assert 'class="view-toggle"' in html
    assert 'data-view="grid"' in html
    assert 'data-view="list"' in html
    assert "@click=\"setView('list')\"" in html

def test_view_persists_in_localstorage():
    assert "localStorage.getItem" in STUDENTS_JS
    assert "localStorage.setItem" in STUDENTS_JS
    assert "opentutorcrm:students-view" in STUDENTS_JS

def test_list_view_class_is_switched_by_alpine(client, owner):
    html = client.get("/tutor/students").text
    assert ":class=\"view === 'list' ? 'students-grid--list' : ''\"" in html
    assert ".students-grid--list {" in STYLES

def test_student_card_page_has_modal_container(client, owner, student_factory):
    """Карточка открывает ту же модалку, значит фабрика должна быть доступна."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    html = client.get(f"/tutor/students/{student_id}").text
    assert 'id="modal"' in html
    assert "/static/students.js" in html
