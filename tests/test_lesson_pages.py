"""Страница уроков: селект цели (3.3) и список с фильтрами (4.1–4.2).

Селект проверяется как e2e: HTTP-клиент проходит тот же путь, что и
браузер, — открытие списка (lookup без `q`), фильтрацию (lookup с `q`),
создание из мини-формы (POST) и «Отменить» (разметка + обработчик без
запроса). Разметка поля рендерится тем же Jinja-окружением, что и в
приложении.
"""

import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.templating import templates
from app.tutor.services.clock import utcnow

PASSWORD = "Секретный-Пароль-1"
ROOT = Path(__file__).resolve().parent.parent
LESSONS_JS = (ROOT / "app" / "static" / "lessons.js").read_text(encoding="utf-8")

RENDER_SELECT = (
    '{% from "lesson/_target_select.html" import target_select %}'
    "{{ target_select(kind) }}"
)


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="lessons-pages@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "lessons-pages@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _render(kind: str) -> str:
    """Разметка компонента селекта (макрос тем же Jinja-окружением)."""
    return templates.env.from_string(RENDER_SELECT).render(kind=kind)


def _options(markup: str) -> list[dict]:
    """Опции фрагмента списка выбора: `data-id` / `data-name`."""
    pairs = re.findall(r'data-id="([^"]+)"\s+data-name="([^"]*)"', markup)
    return [{"id": item_id, "name": name} for item_id, name in pairs]


def _insert_lesson(tutor_id: str, **overrides) -> str:
    """Урок напрямую в БД (для проверки страниц, без формы); возвращает id.

    Без `student_id` в kwargs цель берётся из учеников `tutor_id`;
    для группового урока передайте `student_id=None` и `group_id`.
    """
    with SessionLocal() as db:
        if "student_id" not in overrides:
            student = db.query(Student).filter_by(tutor_id=tutor_id).first()
            overrides["student_id"] = student.id if student else None
        overrides.setdefault("type", "individual")
        overrides.setdefault("starts_at", datetime(2026, 10, 19, 10, 0))
        overrides.setdefault("duration_min", 60)
        overrides.setdefault("status", "planned")
        lesson = Lesson(**overrides)
        db.add(lesson)
        db.commit()
        return str(lesson.id)


# --------------------------------------------------------------------------
# Селект цели урока (3.3)
# --------------------------------------------------------------------------


def test_target_select_opens_list_without_typing(owner, client, student_factory):
    """Список открывается кликом/фокусом и сразу уходит на сервер без ввода."""
    student_factory(tutor_id=owner, first_name="Мария")
    student_factory(tutor_id=owner, first_name="Пётр")

    markup = _render("student")
    assert '@focus="openList()"' in markup
    assert '@click="openList()"' in markup

    # Обработчик открытия не ждёт введённого запроса.
    open_list = re.search(r"openList:\s*function\s*\(\)\s*\{(.*?)\n      \}", LESSONS_JS, re.S)
    assert open_list, "в lessons.js нет openList"
    body = open_list.group(1)
    assert "this.listOpen = true" in body
    assert "refresh()" in body
    assert "query" not in body

    # Как браузер при открытии: lookup без `q` отдаёт весь список выбора.
    response = client.get("/tutor/lessons/lookup/students")
    names = [option["name"] for option in _options(response.text)]
    assert names == ["Мария", "Пётр"]


def test_target_select_typing_filters_open_list(owner, client, student_factory):
    """Ввод фильтрует открытый список: клиент подставляет `q` в lookup."""
    student_factory(tutor_id=owner, first_name="Анна")
    student_factory(tutor_id=owner, first_name="Пётр")

    markup = _render("student")
    assert '@input="onInput($event.target.value)"' in markup

    on_input = re.search(
        r"onInput:\s*function\s*\(value\)\s*\{(.*?)\n      \}", LESSONS_JS, re.S
    )
    assert on_input, "в lessons.js нет onInput"
    body = on_input.group(1)
    assert "this.query = value" in body
    assert "this.listOpen = true" in body

    # Серверная фильтрация тем же эндпоинтом (браузер — с `q`).
    filtered = client.get("/tutor/lessons/lookup/students", params={"q": "анн"})
    assert [option["name"] for option in _options(filtered.text)] == ["Анна"]


def test_target_select_has_divider_and_creation_action(owner):
    """Разделитель и пункт создания в конце списка; мини-форма подменяет поле."""
    student_markup = _render("student")
    assert 'class="combobox__divider"' in student_markup
    assert "Добавить ученика" in student_markup
    assert '@click="openMiniForm()"' in student_markup

    group_markup = _render("group")
    assert "Добавить группу" in group_markup
    # Оба вида: поле и мини-форма подменяют друг друга.
    for markup in (student_markup, group_markup):
        assert 'x-show="!miniOpen"' in markup
        assert 'x-show="miniOpen"' in markup
        # Поля мини-формы без `name` — не уходят в POST формы урока.
        assert 'x-ref="input"' in markup


def test_target_select_e2e_flow(owner, client, student_factory):
    """Сквозной путь селекта: открытие → фильтр → создание → отмена."""
    student_factory(tutor_id=owner, first_name="Мария")

    # 1. Открытие списка: весь выбор.
    opened = client.get("/tutor/lessons/lookup/students")
    assert [option["name"] for option in _options(opened.text)] == ["Мария"]

    # 2. Ввод фильтрует: по «Иван» никто не находится.
    filtered = client.get("/tutor/lessons/lookup/students", params={"q": "Иван"})
    assert _options(filtered.text) == []

    # 3. Мини-форма создаёт ученика и возвращает его в поле селекта.
    created = client.post(
        "/tutor/lessons/students",
        data={"first_name": "Иван", "last_name": "Петров"},
    )
    selected = re.search(r"data-selected='([^']*)'", created.text)
    assert selected, "в ответе мини-формы нет data-selected"
    payload = json.loads(html.unescape(selected.group(1)))
    assert payload["name"] == "Иван Петров"
    student_id = payload["id"]

    # 4. Созданный появился в списке выбора при следующем открытии.
    reopened = client.get("/tutor/lessons/lookup/students")
    assert {"id": student_id, "name": "Иван Петров"} in _options(reopened.text)

    # 5. «Отменить» возвращает поле: обработчик без запроса, БД не меняется.
    markup = _render("student")
    assert '@click="cancelMiniForm()"' in markup
    cancel = re.search(
        r"cancelMiniForm:\s*function\s*\(\)\s*\{(.*?)\n      \}", LESSONS_JS, re.S
    )
    assert cancel and "ajax" not in cancel.group(1)
    with SessionLocal() as db:
        assert db.query(Student).count() == 2  # Мария + созданный Иван


def test_lessons_js_is_served(client):
    """Скрипт компонента отдаётся локально и регистрирует Alpine.data."""
    response = client.get("/static/lessons.js")
    assert response.status_code == 200
    assert 'Alpine.data("lessonTarget"' in response.text
    assert "lesson-target-created" in response.text


# --------------------------------------------------------------------------
# Страница списка уроков (4.1)
# --------------------------------------------------------------------------


def test_lessons_page_requires_session(client):
    """Без входа — редирект на /tutor/login, разметка списка не отдаётся."""
    response = client.get("/tutor/lessons", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert "Уроков пока нет" not in response.text
    assert "Создать урок" not in response.text


def test_lessons_page_empty_state(owner, client):
    """Заголовок, подзаголовок, кнопка создания и пустое состояние."""
    response = client.get("/tutor/lessons")

    assert response.status_code == 200
    assert "<h1>Уроки</h1>" in response.text
    assert "История и управление уроками" in response.text
    assert "Создать урок" in response.text
    assert 'hx-get="/tutor/lessons/new"' in response.text
    assert "Уроков пока нет" in response.text
    # Активный пункт сайдбара — «Уроки».
    active_link = re.search(r'<a[^>]*href="/tutor/lessons"[^>]*>', response.text)
    assert active_link and "nav-item--active" in active_link.group(0)


def _row(page: str, lesson_id: str) -> str:
    """HTML-строка таблицы с данным уроком."""
    match = re.search(
        rf'<tr class="lessons-table__row" id="lesson-row-{re.escape(lesson_id)}[^>]*>.*?</tr>',
        page,
        re.S,
    )
    assert match, f"в списке нет строки урока {lesson_id}"
    return match.group(0)


def test_lessons_page_lists_lessons(owner, client, student_factory, group_factory):
    """Строка урока: цель, чип типа, дата, стоимость, оценка, статус."""
    student = student_factory(
        tutor_id=owner, first_name="Мария", last_name="Иванова"
    )
    group = group_factory(tutor_id=owner, name="Математика 9А")

    individual = _insert_lesson(
        owner,
        student_id=student,
        type="individual",
        starts_at=datetime(2026, 10, 19, 10, 0),
        price=1200,
        status="planned",
    )
    group_lesson = _insert_lesson(
        owner,
        student_id=None,
        group_id=group,
        type="group",
        starts_at=datetime(2026, 10, 21, 15, 30),
        status="completed",
        rating=5,
    )

    page = client.get("/tutor/lessons").text

    # Индивидуальный запланированный урок.
    row = _row(page, individual)
    assert "Мария Иванова" in row
    assert "Индивидуальный" in row
    assert "19.10.2026, 10:00" in row
    assert "1\u00a0200\u00a0₽" in row  # разделители — неразрывные пробелы
    assert "(Оплачено)" not in row  # суффикс — только у проведённых
    assert "Запланирован" in row

    # Групповой проведённый урок: цель — группа, цена «—», оценка, статус.
    row = _row(page, group_lesson)
    assert "Группа: Математика 9А" in row
    assert "Групповой" in row
    assert "21.10.2026, 15:30" in row
    assert "—" in row
    assert "★★★★★" in row
    assert "Проведён" in row


def test_lessons_page_shows_only_own_lessons(
    owner, client, tutor_factory, student_factory
):
    """В списке только свои уроки (изоляция по цели, спека)."""
    other = tutor_factory(email="lessons-other@example.com")
    foreign = student_factory(tutor_id=other, first_name="Чужой")
    _insert_lesson(
        other, student_id=foreign, starts_at=datetime(2026, 10, 19, 9, 0)
    )

    mine = student_factory(tutor_id=owner, first_name="Свой")
    _insert_lesson(owner, student_id=mine, starts_at=datetime(2026, 10, 19, 12, 0))

    page = client.get("/tutor/lessons").text
    assert "Свой" in page
    assert "Чужой" not in page


# --------------------------------------------------------------------------
# Фильтры, поиск и сортировка (4.2)
# --------------------------------------------------------------------------


def _dt(day_offset: int, hour: int = 10, minute: int = 0) -> datetime:
    """Дата относительно сегодня: фильтры «Сегодня»/«На этой неделе» живые.

    «Сегодня» берётся из того же источника, что у приложения (`utcnow`), а
    не из `date.today()`: машина живёт в своей зоне, а фикстура задаёт
    педагогу UTC. В час, когда даты расходятся (после местной полуночи),
    тест падал бы на ровном месте — урок «сегодня» оказывался «вчера».
    """
    day = utcnow().date() + timedelta(days=day_offset)
    return datetime(day.year, day.month, day.day, hour, minute)


def _ids(page: str) -> list[str]:
    """Id уроков в порядке их появления в таблице."""
    return re.findall(r'lessons-table__row" id="lesson-row-([^"]+)"', page)


def test_lessons_filter_ui_present(owner, client, student_factory):
    """Панель фильтров: поиск, выбор ученика и чипы периода (спека)."""
    student_factory(tutor_id=owner, first_name="Мария")

    page = client.get("/tutor/lessons").text

    assert 'hx-get="/tutor/lessons/list"' in page
    assert 'id="lessons-filters"' in page
    assert 'name="q"' in page
    assert "Все ученики" in page
    assert "Мария" in page  # список фильтра — свои ученики
    for label in ("Все", "Сегодня", "На этой неделе"):
        assert f">{label}</span>" in page


def test_lessons_filter_today(owner, client, student_factory):
    """Чип «Сегодня»: остаются только уроки сегодняшнего дня."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    today = _insert_lesson(owner, student_id=student, starts_at=_dt(0, 10, 0))
    tomorrow = _insert_lesson(owner, student_id=student, starts_at=_dt(1, 10, 0))

    response = client.get("/tutor/lessons", params={"period": "today"})
    ids = _ids(response.text)
    assert today in ids
    assert tomorrow not in ids

    # Тот же фильтр работает партиалом HTMX.
    partial = client.get("/tutor/lessons/list", params={"period": "today"})
    assert today in _ids(partial.text)
    assert tomorrow not in partial.text


def test_lessons_filter_today_keeps_near_midnight_lesson(
    client, tutor_factory, student_factory
):
    """Спека (задача 5.2): урок около полуночи попадает в свой день.

    Урок в 23:30 местного времени (UTC+04) хранится как 19:30 UTC; фильтр
    «Сегодня» считает день по зоне педагога, поэтому урок остаётся в своём
    дне, а не уезжает в следующий из-за перевода в UTC.
    """
    email = "lessons-pages-midnight@example.com"
    owner = tutor_factory(
        email=email, password=PASSWORD, timezone="Europe/Ulyanovsk"
    )
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    student = student_factory(tutor_id=owner, first_name="Мария")
    # Локальное «сегодня» в 23:30 → в UTC это сегодня же в 19:30 (UTC+04).
    # Дата — из зоны педагога, а не с машины: в час расхождения дат
    # `date.today()` дал бы «завтра» и урок выпал бы из фильтра.
    local_today = datetime.now(ZoneInfo("Europe/Ulyanovsk")).date()
    today_late = _insert_lesson(
        owner,
        student_id=student,
        starts_at=datetime.combine(local_today, datetime.min.time()).replace(
            hour=19, minute=30
        ),
    )

    ids = _ids(
        client.get("/tutor/lessons", params={"period": "today"}).text
    )
    assert today_late in ids


def test_lessons_filter_week(owner, client, student_factory):
    """Чип «На этой неделе»: понедельник — воскресенье текущей недели."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    # Неделя — по зоне педагога (фикстура задаёт UTC), а не по зоне машины:
    # иначе в час расхождения дат «сегодня» теста попадало в чужую неделю.
    today = utcnow().date()
    monday = today - timedelta(days=today.weekday())
    # День текущей недели, отличный от сегодняшнего.
    in_week_day = monday + timedelta(days=(today.weekday() + 2) % 7)
    in_week = datetime(in_week_day.year, in_week_day.month, in_week_day.day, 11, 0)
    beyond = monday + timedelta(days=7)  # понедельник следующей недели

    inside = _insert_lesson(owner, student_id=student, starts_at=in_week)
    current = _insert_lesson(owner, student_id=student, starts_at=_dt(0, 9, 0))
    outside = _insert_lesson(
        owner,
        student_id=student,
        starts_at=datetime(beyond.year, beyond.month, beyond.day, 11, 0),
    )

    ids = _ids(client.get("/tutor/lessons", params={"period": "week"}).text)
    assert inside in ids
    assert current in ids
    assert outside not in ids


def test_lessons_filter_by_student(owner, client, student_factory):
    """Фильтр по ученику: остаются только его уроки."""
    anna = student_factory(tutor_id=owner, first_name="Анна")
    peter = student_factory(tutor_id=owner, first_name="Пётр")
    anna_lesson = _insert_lesson(
        owner, student_id=anna, starts_at=_dt(0, 10, 0)
    )
    peter_lesson = _insert_lesson(
        owner, student_id=peter, starts_at=_dt(0, 12, 0)
    )

    ids = _ids(client.get("/tutor/lessons", params={"student": anna}).text)
    assert anna_lesson in ids
    assert peter_lesson not in ids

    # Пустое значение — снова все уроки.
    ids = _ids(client.get("/tutor/lessons", params={"student": ""}).text)
    assert anna_lesson in ids and peter_lesson in ids


def test_lessons_search(owner, client, student_factory):
    """Поиск по цели и заметке, без учёта регистра."""
    anna = student_factory(tutor_id=owner, first_name="Анна", last_name="Иванова")
    peter = student_factory(tutor_id=owner, first_name="Пётр")
    by_name = _insert_lesson(owner, student_id=anna, starts_at=_dt(0, 10, 0))
    by_note = _insert_lesson(
        owner, student_id=peter, starts_at=_dt(0, 12, 0), note="Подготовка к ОГЭ"
    )

    ids = _ids(
        client.get("/tutor/lessons", params={"q": "ИВАНОВ"}).text
    )
    assert by_name in ids
    assert by_note not in ids

    ids = _ids(client.get("/tutor/lessons", params={"q": "огэ"}).text)
    assert ids == [by_note]


def test_lessons_filters_combine(owner, client, student_factory):
    """Комбинирование: период + ученик + поиск работают вместе."""
    anna = student_factory(tutor_id=owner, first_name="Анна")
    peter = student_factory(tutor_id=owner, first_name="Пётр")
    wanted = _insert_lesson(
        owner,
        student_id=anna,
        starts_at=_dt(0, 10, 0),
        note="Сумма дробей",
    )
    wrong_student = _insert_lesson(
        owner,
        student_id=peter,
        starts_at=_dt(0, 11, 0),
        note="Сумма дробей",
    )
    wrong_day = _insert_lesson(
        owner,
        student_id=anna,
        starts_at=_dt(30),
        note="Сумма дробей",
    )

    ids = _ids(
        client.get(
            "/tutor/lessons",
            params={"period": "today", "student": anna, "q": "дробей"},
        ).text
    )
    assert ids == [wanted]
    assert wrong_student not in ids
    assert wrong_day not in ids

    # Неизвестное значение периода схлопывается в «Все» — без ошибки 500.
    response = client.get("/tutor/lessons", params={"period": "bogus"})
    assert response.status_code == 200
    assert len(_ids(response.text)) == 3


def test_lessons_default_sort_nearest_first(owner, client, student_factory):
    """По умолчанию — «Сначала ближайшие»: по времени начала, по возрастанию."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    later = _insert_lesson(owner, student_id=student, starts_at=_dt(10, 10, 0))
    earlier = _insert_lesson(owner, student_id=student, starts_at=_dt(-10, 10, 0))
    middle = _insert_lesson(owner, student_id=student, starts_at=_dt(0, 15, 0))

    page = client.get("/tutor/lessons").text
    order = _ids(page)
    assert [earlier, middle, later] == [
        lesson_id for lesson_id in order if lesson_id in (earlier, middle, later)
    ]

    # Порядок тот же в партиале фильтров.
    partial = client.get("/tutor/lessons/list").text
    assert _ids(partial) == order


def test_lessons_list_partial_requires_session(client):
    """Без входа партиал фильтров отвечает редиректом, без уроков."""
    response = client.get("/tutor/lessons/list", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert "lessons-table" not in response.text


# --------------------------------------------------------------------------
# Часовой пояс: смена зоны и некорректное значение (спека tutor-timezone)
# --------------------------------------------------------------------------


def test_changing_timezone_changes_display_but_not_stored_value(
    client, tutor_factory, student_factory
):
    """Спека: смена зоны меняет только показ, данные не переписываются.

    Урок хранится как `06:00 UTC`. При зоне UTC+04 он показан как 10:00,
    после смены зоны на UTC+07 — как 13:00, а в БД остаётся `06:00`.
    """
    email = "lessons-pages-zone-shift@example.com"
    owner = tutor_factory(
        email=email, password=PASSWORD, timezone="Europe/Ulyanovsk"
    )
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    student = student_factory(tutor_id=owner, first_name="Мария")
    lesson_id = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 22, 6, 0)
    )

    assert "22.10.2026, 10:00" in _row(client.get("/tutor/lessons").text, lesson_id)

    # Меняем зону в карточке — только отображение.
    with SessionLocal() as db:
        from app.tutor.models.tutor import Tutor

        db.get(Tutor, owner).timezone = "Asia/Krasnoyarsk"
        db.commit()

    assert "22.10.2026, 13:00" in _row(client.get("/tutor/lessons").text, lesson_id)

    # Хранимое значение не изменилось.
    with SessionLocal() as db:
        assert db.get(Lesson, lesson_id).starts_at == datetime(2026, 10, 22, 6, 0)


def test_unknown_timezone_does_not_break_pages(
    client, tutor_factory, student_factory
):
    """Спека: некорректное имя зоны не роняет показ — берётся системная зона."""
    email = "lessons-pages-bad-zone@example.com"
    owner = tutor_factory(
        email=email, password=PASSWORD, timezone="No/Such_Zone"
    )
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    student = student_factory(tutor_id=owner, first_name="Мария")
    lesson_id = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 22, 6, 0)
    )

    response = client.get("/tutor/lessons")

    assert response.status_code == 200
    # Строка урока отрисована: страница не упала на неизвестной зоне.
    assert _row(response.text, lesson_id)
    # Календарь и модалка тоже открываются.
    assert client.get("/tutor/calendar?start=2026-10-19").status_code == 200
    assert client.get(f"/tutor/lessons/{lesson_id}/edit").status_code == 200
