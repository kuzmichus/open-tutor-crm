"""Тесты разметки страницы учеников и её стилей.

Покрывают задачи 7.1–7.6: шапка страницы и контейнеры, состав карточки,
честные заглушки вместо выдуманных метрик, наличие CSS для всех классов
из новых шаблонов и адаптив сетки.
"""

import re
from datetime import UTC, datetime
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


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="ui-owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "ui-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _css_block(selector: str) -> str:
    """Тело правила `selector { ... }` с учётом вложенных блоков."""
    start = STYLES.index(f"{selector} {{")
    depth = 0
    for index in range(start, len(STYLES)):
        char = STYLES[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return STYLES[start : index + 1]
    raise AssertionError(f"Не закрыт блок {selector}")


def _card_article(html: str) -> str:
    """HTML одной карточки ученика — без сайдбара и нижнего меню."""
    start = html.index('<article class="student-card"')
    return html[start : html.index("</article>", start)]


# --------------------------------------------------------------------------
# 7.1 Страница списка
# --------------------------------------------------------------------------


def test_list_page_has_header_grid_and_add_button(client, owner):
    response = client.get("/tutor/students")
    html = response.text

    assert 'class="sidebar"' in html
    assert "nav-item--active" in html
    assert 'id="students-grid"' in html
    assert 'id="modal"' in html
    assert "page-header--row" in html
    assert "Добавить ученика" in html
    assert 'hx-get="/tutor/students/new"' in html


def test_sidebar_highlights_students(client, owner):
    """Активен именно пункт «Ученики», а не первый пункт меню."""
    html = client.get("/tutor/students").text
    active = re.search(r'<a href="([^"]+)"\s+class="nav-item nav-item--active"', html)
    assert active, "В сайдбаре нет активного пункта"
    assert active.group(1) == "/tutor/students"


# --------------------------------------------------------------------------
# 7.2 Состав карточки
# --------------------------------------------------------------------------


def test_card_shows_both_contact_roles(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    with SessionLocal() as db:
        mom = Contact(tutor_id=owner, full_name="Мама Ольга")
        granny = Contact(tutor_id=owner, full_name="Бабушка Нина")
        db.add_all([mom, granny])
        db.commit()
        db.add_all(
            [
                StudentContact(
                    student_id=student_id,
                    contact_id=mom.id,
                    relation="мама",
                    remind_lesson=True,
                ),
                StudentContact(
                    student_id=student_id, contact_id=granny.id, relation="бабушка"
                ),
            ]
        )
        db.commit()

    card = _card_article(client.get("/tutor/students").text)
    assert "Мама Ольга" in card and "мама" in card
    assert "Бабушка Нина" in card and "бабушка" in card
    # Признак получателя напоминаний — только у мамы.
    assert card.count("напоминания") == 1


def test_card_without_contacts_renders(client, owner, student_factory):
    student_factory(tutor_id=owner, first_name="Одинокий")
    card = _card_article(client.get("/tutor/students").text)
    assert "Одинокий" in card
    assert "платит сам ученик" in card


def test_card_shows_initials_and_status_chip(client, owner, student_factory):
    student_factory(tutor_id=owner, first_name="Маша", last_name="Петрова", status="new")
    card = _card_article(client.get("/tutor/students").text)

    assert 'class="avatar"' in card
    assert "МП" in card
    assert "chip--new" in card


def test_card_hides_grade_and_school_for_adult(client, owner, student_factory):
    student_factory(
        tutor_id=owner,
        first_name="Взрослый",
        kind="adult",
        grade=11,
        school="Школа",
    )
    card = _card_article(client.get("/tutor/students").text)
    assert "Школа" not in card


# --------------------------------------------------------------------------
# Сводка счёта на странице ученика (задача 9.1, design D12)
# --------------------------------------------------------------------------


def test_stub_block_has_no_invented_numbers_or_dead_links(client, owner, student_factory):
    student_factory(tutor_id=owner, first_name="Маша")
    card = _card_article(client.get("/tutor/students").text)

    assert "student-metrics" in card
    for forbidden in ("0 ₽", "Проведено", "/lessons", "/report", 'href="#"'):
        assert forbidden not in card, f"В карточке не должно быть {forbidden!r}"


def test_card_page_shows_balance_summary(client, owner, student_factory):
    """Вместо заглушки «Уроки и оплаты» — настоящий баланс ученика."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    html = client.get(f"/tutor/students/{student_id}").text

    assert "Уроки и оплаты" not in html
    assert "Счёт ученика" in html
    # Ученик без операций: баланс ноль, и это единственное честное число.
    assert "Баланс ученика" in html
    assert "0\u00a0₽" in html
    assert "Операций пока нет" in html


def test_card_page_shows_balance_from_operations(
    client, owner, student_factory, operation_factory
):
    """Платёж 2000 и списание 1200 дают баланс 800 на странице ученика."""
    from app.database import SessionLocal
    from app.lesson.models.lesson import Lesson

    student_id = student_factory(tutor_id=owner, first_name="Маша")
    operation_factory(student_id=student_id, amount=2000)
    with SessionLocal() as session:
        session.add(
            Lesson(
                student_id=student_id,
                type="individual",
                starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
                duration_min=60,
                price=1200,
                status="completed",
            )
        )
        session.commit()
    client.post(f"/tutor/students/{student_id}/balance/recalculate")

    html = client.get(f"/tutor/students/{student_id}").text
    start = html.index("Счёт ученика")
    block = html[start : html.index("</section>", start)]

    assert "800\u00a0₽" in block
    assert "+2\u00a0000\u00a0₽" in block
    assert "\u22121\u00a0200\u00a0₽" in block


def test_card_page_has_payments_action(client, owner, student_factory):
    """Действие «Платежи» открывает карточку на вкладке «Платежи»."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    html = client.get(f"/tutor/students/{student_id}").text

    start = html.index("Счёт ученика")
    block = html[start : html.index("</section>", start)]

    assert (
        f'hx-get="/tutor/students/{student_id}/edit?from_card=1&tab=payments"'
        in block
    )
    assert 'hx-target="#modal"' in block
    assert "Платежи" in block
    # Ни одной выдуманной метрики в сводке.
    for forbidden in ("Проведено", "/lessons", "/report", 'href="#"'):
        assert forbidden not in block


# --------------------------------------------------------------------------
# 7.4 / 7.5 Классы из шаблонов описаны в styles.css
# (полная проверка «каждый класс шаблона есть в CSS» — в test_css_styles.py)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "selector",
    [
        ".students-grid",
        ".student-card",
        ".student-head",
        ".student-id",
        ".avatar",
        ".student-name",
        ".student-contacts",
        ".student-metrics",
        ".student-actions",
        ".students-card",
        ".card-header",
        ".filters",
        ".view-toggle",
        ".empty-state",
        ".page-header--row",
    ],
)
def test_component_rules_exist(selector):
    assert f"{selector} {{" in STYLES, f"В styles.css нет правила {selector}"


@pytest.mark.parametrize(
    "utility",
    [
        ".hide-sm",
        ".show-sm",
        ".grow",
        ".flex-1",
        ".span-2",
        ".justify-between",
        ".btn--outline",
        ".btn--sm",
        ".chip--new",
        ".chip--active",
        ".chip--archived",
    ],
)
def test_utility_rules_exist(utility):
    assert f"{utility} {{" in STYLES or f"{utility} " in STYLES, (
        f"В styles.css нет правила {utility}"
    )


def test_students_block_uses_tokens_not_literal_colors():
    """Цвета компонентов учеников — только через токены, иначе сломается тема."""
    block = STYLES[
        STYLES.index("Страница учеников: сетка карточек") : STYLES.index(
            "Модальное окно и секции формы"
        )
    ]
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", block)
    assert not literals, f"Литеральные цвета в блоке учеников: {literals}"


# --------------------------------------------------------------------------
# 7.6 Адаптив
# --------------------------------------------------------------------------


def test_grid_is_three_two_one_columns():
    grid = _css_block(".students-grid")

    assert "grid-template-columns: 1fr;" in grid
    assert re.search(r"@media \(min-width: 640px\).*repeat\(2,", grid, re.S)
    assert re.search(r"@media \(min-width: 1024px\).*repeat\(3,", grid, re.S)


# --------------------------------------------------------------------------
# 7.7 Вид «список»: таблица зеброй, клик открывает редактирование
# --------------------------------------------------------------------------


def _list_table(html: str) -> str:
    """HTML таблицы списка — до закрывающего `</table>`."""
    start = html.index('<table class="students-table"')
    return html[start : html.index("</table>", start)]


def test_list_view_table_has_required_columns(client, owner, student_factory):
    """Таблица списка: имя, контакты (телефон + почта) и статус."""
    student_factory(
        tutor_id=owner,
        first_name="Маша",
        last_name="Петрова",
        phone="+7 999 111-22-33",
        email="masha@example.com",
        status="active",
    )
    table = _list_table(client.get("/tutor/students").text)

    assert table.count("<th ") == 3
    for heading in ("Имя", "Контакты", "Статус"):
        assert f">{heading}</th>" in table
    assert "Маша Петрова" in table
    assert "+7 999 111-22-33" in table
    assert "masha@example.com" in table
    assert "chip--active" in table


def test_list_view_table_shows_placeholder_without_contacts(
    client, owner, student_factory
):
    """Без телефона и почты — прочерк, а не пустая ячейка."""
    student_factory(tutor_id=owner, first_name="Одинокий")
    table = _list_table(client.get("/tutor/students").text)

    assert "students-table__contact--empty" in table


def test_list_view_row_opens_edit_form(client, owner, student_factory):
    """Строка таблицы грузит форму редактирования в модалку страницы."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    table = _list_table(client.get("/tutor/students").text)

    row = table[table.index(f'id="student-row-{student_id}"') :]
    assert 'hx-get="/tutor/students/' in row
    assert "/edit\"" in row
    assert 'hx-target="#modal"' in row
    assert "keydown[key=='Enter']" in row
    assert 'tabindex="0"' in row


def test_list_partial_renders_table_too(client, owner, student_factory):
    """Поиск и фильтр возвращают ту же таблицу: htmx-партиал полный."""
    student_factory(tutor_id=owner, first_name="Маша")
    partial = client.get("/tutor/students/list", params={"q": "маша"}).text

    assert '<table class="students-table"' in partial
    assert "Маша" in partial


def test_table_is_zebra_striped_in_css():
    """Чётные строки подсвечены вторым фоном (только токены, не цвета)."""
    row = _css_block(".students-table__row")

    assert "&:nth-child(even)" in row
    assert "background: var(--muted)" in row
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", row)
    assert not literals, f"Литеральные цвета в строке таблицы: {literals}"


def test_table_is_hidden_in_grid_mode_and_shown_in_list_mode(
    client, owner, student_factory
):
    """Вид переключается CSS-классом на контейнере: обе разметки в DOM."""
    student_factory(tutor_id=owner, first_name="Маша")
    html = client.get("/tutor/students").text

    # Таблица отдаётся всегда, но по умолчанию скрыта (вложенный блок
    # `.students-grid--list .students-table-wrap` её снова показывает).
    assert '<table class="students-table"' in html
    wraps = re.findall(r"\.students-table-wrap \{([^}]*)\}", STYLES)
    assert wraps, "В styles.css нет правила .students-table-wrap"
    assert any("display: none;" in body for body in wraps)
    # А в виде «список» её показывает тот же Alpine-класс, что прячет карточки.
    list_mode = _css_block(".students-grid--list")
    assert "& .students-table-wrap" in list_mode
    assert "display: block;" in list_mode
    assert "& .student-card" in list_mode
    assert "display: none;" in list_mode


def test_filters_collapse_on_mobile_with_toggle(client, owner):
    html = client.get("/tutor/students").text

    # Панель фильтров скрыта на телефоне и раскрывается кнопкой.
    assert re.search(
        r"@media \(max-width: 639\.98px\).*\.filters \{\s*display: none;", STYLES, re.S
    )
    assert "&.is-open { display: flex; }" in STYLES
    # Кнопка-переключатель видна именно на телефоне.
    assert re.search(r"\.show-sm \{ display: inline-flex; \}", STYLES)
    assert re.search(r'class="[^"]*show-sm[^"]*"[^>]*@click="filtersOpen', html)
    assert 'aria-controls="students-filters"' in html
