"""Селекты цели урока: поиск (3.1) и мини-формы создания (3.2).

Тесты идут через HTTP-клиент, как браузер: GET lookup-эндпоинтов — это
открытие списка и ввод в поле, POST мини-форм — создание записи.
"""

import html
import json
import re

from app.common.colors import PALETTE

PASSWORD = "Секретный-Пароль-1"


def _owner(client, tutor_factory, email: str) -> str:
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _options(markup: str) -> list[dict]:
    """`data-id` / `data-name` всех опций фрагмента списка выбора."""
    pairs = re.findall(
        r'data-id="([^"]+)"\s+data-name="([^"]*)"', markup
    )
    return [{"id": item_id, "name": name} for item_id, name in pairs]


# --------------------------------------------------------------------------
# Поиск для селекта (3.1)
# --------------------------------------------------------------------------


def test_lookup_students_returns_own_active_only(
    client, tutor_factory, student_factory
):
    """В выборе — только свои ученики; архивные и чужие не отдаются."""
    owner = _owner(client, tutor_factory, "lookup-owner@example.com")
    active = student_factory(tutor_id=owner, first_name="Мария")
    student_factory(tutor_id=owner, first_name="Архивный", status="archived")
    other_tutor = tutor_factory(email="lookup-other@example.com")
    student_factory(tutor_id=other_tutor, first_name="Чужой")

    response = client.get("/tutor/lessons/lookup/students")

    assert response.status_code == 200
    names = [option["name"] for option in _options(response.text)]
    assert names == ["Мария"]
    assert _options(response.text)[0]["id"] == active
    assert "Архивный" not in response.text
    assert "Чужой" not in response.text


def test_lookup_students_filters_by_name(client, tutor_factory, student_factory):
    """Ввод фильтрует: совпадение без учёта регистра, пусто — «Ничего»."""
    owner = _owner(client, tutor_factory, "lookup-q@example.com")
    student_factory(tutor_id=owner, first_name="Анна", last_name="Иванова")
    student_factory(tutor_id=owner, first_name="Пётр", last_name="Сидоров")

    found = client.get("/tutor/lessons/lookup/students", params={"q": "аннА"})
    assert [option["name"] for option in _options(found.text)] == ["Анна Иванова"]

    none = client.get("/tutor/lessons/lookup/students", params={"q": "Борис"})
    assert _options(none.text) == []
    assert "Ничего не найдено" in none.text


def test_lookup_groups_returns_own_groups_by_name(
    client, tutor_factory, group_factory
):
    """В выборе групп — только свои, поиск по названию."""
    owner = _owner(client, tutor_factory, "lookup-groups@example.com")
    keep = group_factory(tutor_id=owner, name="Математика 9А")
    group_factory(tutor_id=owner, name="Физика 8Б")
    other_tutor = tutor_factory(email="lookup-groups-other@example.com")
    group_factory(tutor_id=other_tutor, name="Чужая группа")

    found = client.get("/tutor/lessons/lookup/groups", params={"q": "матем"})
    assert _options(found.text) == [{"id": keep, "name": "Математика 9А"}]

    all_groups = client.get("/tutor/lessons/lookup/groups")
    names = [option["name"] for option in _options(all_groups.text)]
    assert "Чужая группа" not in names
    assert "Физика 8Б" in names


def test_lookup_requires_session(client):
    """Без сессии lookup отвечает редиректом на вход, без данных выбора."""
    response = client.get(
        "/tutor/lessons/lookup/students", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert "data-id" not in response.text


# --------------------------------------------------------------------------
# Мини-формы создания (3.2)
# --------------------------------------------------------------------------


def _selected(markup: str) -> dict | None:
    """JSON `data-selected` транспортного фрагмента ответа мини-формы."""
    match = re.search(r"data-selected='([^']*)'", markup)
    assert match, "в ответе нет data-selected"
    value = json.loads(html.unescape(match.group(1)))
    return value if isinstance(value, dict) else None


def _error(markup: str) -> str:
    """`data-error` транспортного фрагмента ответа мини-формы."""
    match = re.search(r'data-error="([^"]*)"', markup)
    assert match, "в ответе нет data-error"
    return html.unescape(match.group(1))


def _render_target(kind: str) -> str:
    """Разметка компонента селекта — макрос рендерится тем же Jinja-окружением."""
    from app.templating import templates

    source = (
        '{% from "lesson/_target_select.html" import target_select %}'
        "{{ target_select(kind) }}"
    )
    return templates.env.from_string(source).render(kind=kind)


def test_mini_form_creates_student_and_returns_selection(
    client, tutor_factory, student_factory
):
    """Мини-форма ученика создаёт запись и возвращает её в поле селекта."""
    from app.database import SessionLocal
    from app.student.models.student import Student

    owner = _owner(client, tutor_factory, "mini-student@example.com")

    response = client.post(
        "/tutor/lessons/students",
        data={
            "first_name": "Пётр",
            "last_name": "Сидоров",
            "phone": "8 916 123-45-67",
        },
    )

    assert response.status_code == 200
    assert 'id="lesson-target-update-student"' in response.text
    selected = _selected(response.text)
    assert selected["name"] == "Пётр Сидоров"
    with SessionLocal() as db:
        student = db.get(Student, selected["id"])
        assert student.tutor_id == owner
        assert student.status == "new"
        assert student.kind == "child"
        assert student.phone is not None  # телефон нормализован
        # Мини-форма назначает цвет из палитры (1.4).
        assert student.color in PALETTE


def test_mini_form_student_requires_name(client, tutor_factory):
    """Пустое имя: ученик не создаётся, ошибка в `data-error`."""
    from app.database import SessionLocal
    from app.student.models.student import Student

    _owner(client, tutor_factory, "mini-student-empty@example.com")

    response = client.post(
        "/tutor/lessons/students", data={"first_name": "   "}
    )

    assert _error(response.text) == "Укажите имя ученика."
    assert _selected(response.text) is None
    with SessionLocal() as db:
        assert db.query(Student).count() == 0


def test_mini_form_creates_group_with_price(client, tutor_factory):
    """Мини-форма группы создаёт запись с ценой и возвращает её в селект."""
    from app.database import SessionLocal
    from app.group.models.group import Group

    owner = _owner(client, tutor_factory, "mini-group@example.com")

    response = client.post(
        "/tutor/lessons/groups",
        data={"name": "Математика 9А", "price": "1200"},
    )

    assert response.status_code == 200
    assert 'id="lesson-target-update-group"' in response.text
    selected = _selected(response.text)
    assert selected["name"] == "Математика 9А"
    with SessionLocal() as db:
        group = db.get(Group, selected["id"])
        assert group.tutor_id == owner
        assert group.price_per_lesson == 1200


def test_mini_form_group_requires_name(client, tutor_factory):
    """Пустое название (спека): группа не создаётся, поле — ошибка."""
    from app.database import SessionLocal
    from app.group.models.group import Group

    _owner(client, tutor_factory, "mini-group-empty@example.com")

    response = client.post(
        "/tutor/lessons/groups", data={"name": "", "price": "900"}
    )

    assert _error(response.text) == "Укажите название группы."
    assert _selected(response.text) is None
    with SessionLocal() as db:
        assert db.query(Group).count() == 0


def test_mini_form_group_rejects_non_numeric_price(client, tutor_factory):
    """Цена не числом — валидация создания группы, ошибка в ответе."""
    from app.database import SessionLocal
    from app.group.models.group import Group

    _owner(client, tutor_factory, "mini-group-price@example.com")

    response = client.post(
        "/tutor/lessons/groups", data={"name": "Физика", "price": "дорого"}
    )

    assert "Цена за урок" in _error(response.text)
    with SessionLocal() as db:
        assert db.query(Group).count() == 0


def test_mini_form_requires_session(client):
    """Без сессии мини-формы ничего не создают — редирект на вход."""
    from app.database import SessionLocal
    from app.group.models.group import Group
    from app.student.models.student import Student

    response = client.post(
        "/tutor/lessons/students",
        data={"first_name": "Пётр"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"

    with SessionLocal() as db:
        assert db.query(Student).count() == 0
        assert db.query(Group).count() == 0


def test_mini_form_cancel_returns_field_and_creates_nothing(client, tutor_factory):
    """«Отменить» возвращает поле без изменений: ничего не создаётся.

    Отмена — клиентское действие (`cancelMiniForm` в `lessons.js`), сервер
    в этот момент вообще не вызывается: тест держит разметку поля и тело
    обработчика, а также то, что после отмены в БД пусто.
    """
    from app.database import SessionLocal
    from app.group.models.group import Group
    from app.student.models.student import Student

    _owner(client, tutor_factory, "mini-cancel@example.com")
    markup = _render_target("student")

    # Поле подменяется мини-формой и возвращается по «Отменить».
    assert 'x-show="!miniOpen"' in markup
    assert 'x-show="miniOpen"' in markup
    assert '@click="cancelMiniForm()"' in markup
    assert "Отменить" in markup

    # Обработчик отмены закрывает форму и не ходит на сервер.
    from pathlib import Path

    js_path = Path(__file__).resolve().parent.parent / "app" / "static" / "lessons.js"
    js = js_path.read_text(encoding="utf-8")
    body = re.search(
        r"cancelMiniForm:\s*function\s*\(\)\s*\{(.*?)\n      \}", js, re.S
    )
    assert body, "в lessons.js нет cancelMiniForm"
    assert "miniOpen = false" in body.group(1)
    assert "ajax" not in body.group(1)
    assert "createUrl" not in body.group(1)

    # Записей не появилось: отмена не создавала ни ученика, ни группу.
    with SessionLocal() as db:
        assert db.query(Student).count() == 0
        assert db.query(Group).count() == 0
