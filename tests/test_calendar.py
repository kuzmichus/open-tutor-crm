"""Тесты календаря: unit-тесты демо-генератора и страницы GET /tutor/calendar.

Имена unit-тестов генератора содержат «demo», чтобы их можно было отобрать
фильтром `uv run pytest tests/test_calendar.py -k demo`.
"""

import re
from datetime import date, datetime, time
from pathlib import Path

import pytest

from app.calendar.services.demo_schedule import (
    VACATION,
    build_week,
    is_between_terms,
    lessons_word,
    week_start,
)

# «Демо-неделя» без особых периодов (середина октября 2026).
_PLAIN_MONDAY = date(2026, 10, 12)

PASSWORD = "Секретный-Пароль-1"


def _login(client, email="calendar-user@example.com"):
    """Регистрирует репетитора и открывает сессию в клиенте."""
    client.post(
        "/tutor/register",
        data={
            "name": "Календарный",
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


@pytest.fixture()
def calendar_owner(client):
    """Репетитор, вошедший в клиент; возвращает его id для уроков в БД."""
    client.post(
        "/tutor/register",
        data={
            "name": "Календарный",
            "email": "calendar-owner@example.com",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )
    client.post(
        "/tutor/login",
        data={"email": "calendar-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    from app.database import SessionLocal
    from app.tutor.models.tutor import Tutor

    with SessionLocal() as db:
        return db.query(Tutor).filter_by(email="calendar-owner@example.com").one().id


def _insert_lesson(tutor_id: str, **overrides) -> str:
    """Урок напрямую в БД (без формы); возвращает его id.

    Без `student_id` в kwargs цель берётся из первого ученика репетитора;
    для группового урока передайте `student_id=None` и `group_id`.
    """
    from app.database import SessionLocal
    from app.lesson.models.lesson import Lesson
    from app.student.models.student import Student

    with SessionLocal() as db:
        if "student_id" not in overrides:
            student = db.query(Student).filter_by(tutor_id=tutor_id).first()
            overrides["student_id"] = student.id if student else None
        overrides.setdefault("type", "individual")
        overrides.setdefault("starts_at", datetime(2026, 10, 14, 14, 0))
        overrides.setdefault("duration_min", 40)
        overrides.setdefault("status", "planned")
        lesson = Lesson(**overrides)
        db.add(lesson)
        db.commit()
        return str(lesson.id)


# --------------------------------------------------------------------------
# 3.1 Доступ: без сессии — редирект на вход
# --------------------------------------------------------------------------

def test_calendar_requires_session(client):
    """Без сессии GET /tutor/calendar → 303 на /tutor/login."""
    response = client.get("/tutor/calendar", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


# --------------------------------------------------------------------------
# 3.2 Полная страница: панель, шапка дней, таймлайн
# --------------------------------------------------------------------------

def test_calendar_full_page_renders(client):
    """Входящий видит полную страницу с панелью управления."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert response.status_code == 200
    for label in ("Сегодня", "Добавить", "Ссылка на окна", "Цвет: по ученику"):
        assert label in response.text


def test_calendar_range_title(client):
    """Заголовок панели — диапазон семи дней недели."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "12 октября – 18 октября 2026" in response.text


def test_calendar_timeline_labels(client):
    """Таймлайн: целый час крупно («6:00»), половина — мелким («6:30»)."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "6:00" in response.text
    assert "6:30" in response.text
    assert "23:00" in response.text


def test_calendar_weekend_badge(client, calendar_owner, student_factory):
    """Сб/вс отмечены плашкой «Выходной»; будни — числами занятий."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Иван")
    _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 12, 10, 0),
    )
    _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 12, 17, 0),
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "Выходной" in response.text
    assert "2 урока" in response.text  # понедельник: два урока репетитора


def test_calendar_timezone_badge_hidden_without_timezone(client, tutor_factory):
    """Пустое поле timezone — элемент часового пояса отсутствует."""
    tutor_factory(email="no-tz@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "no-tz@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert 'class="cal-tz"' not in response.text


def test_calendar_timezone_badge_shown_when_set(client, tutor_factory):
    """Заданный timezone виден в панели управления."""
    tutor_factory(
        email="with-tz@example.com",
        password=PASSWORD,
        timezone="Europe/Samara",
    )
    client.post(
        "/tutor/login",
        data={"email": "with-tz@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "Europe/Samara" in response.text


# --------------------------------------------------------------------------
# 3.3 Карточки занятий и состояние сетки (реальные уроки из БД)
# --------------------------------------------------------------------------

def test_calendar_event_card_content(client, calendar_owner, student_factory):
    """Карточка урока: имя с ценой и интервал времени вида «14:00 – 14:40»."""
    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Иван", last_name="Иванов"
    )
    _insert_lesson(
        calendar_owner,
        student_id=student_id,
        starts_at=datetime(2026, 10, 14, 14, 0),
        duration_min=40,
        price=1200,
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "Иван И." in response.text
    assert "14:00 – 14:40" in response.text  # среда недели


def test_calendar_overlapping_events_shifted(client, calendar_owner, student_factory):
    """Пересекающиеся уроки среды накладываются со сдвигом (left/width)."""
    first = student_factory(tutor_id=calendar_owner, first_name="Иван")
    second = student_factory(tutor_id=calendar_owner, first_name="Ольга")
    _insert_lesson(
        calendar_owner, student_id=first,
        starts_at=datetime(2026, 10, 14, 14, 0), duration_min=40,
    )
    _insert_lesson(
        calendar_owner, student_id=second,
        starts_at=datetime(2026, 10, 14, 14, 20), duration_min=40,
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    # Оба урока присутствуют, у первого и второго разные смещения/ширины.
    assert "14:00 – 14:40" in response.text
    assert "14:20 – 15:00" in response.text
    assert "--left: 0%" in response.text
    assert "--left: 50%" in response.text
    assert "--width: 50%" in response.text


def test_calendar_vacation_block(client):
    """Август — блок «Отпуск» вместо занятий."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-08-03")
    assert response.status_code == 200
    assert "Отпуск" in response.text


def test_calendar_weekend_hatching(client):
    """Колонки сб/вс помечены штриховкой выходных."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert 'class="cal-day cal-day--weekend"' in response.text


def test_calendar_empty_week_renders(client, calendar_owner, student_factory):
    """Неделя без уроков: страница без ошибки, пояснение о свободной неделе."""
    # Уроки есть, но на другой неделе — запрошенная остаётся пустой.
    student_id = student_factory(tutor_id=calendar_owner, first_name="Иван")
    _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 14, 14, 0),
    )
    response = client.get("/tutor/calendar?start=2026-11-09")
    assert response.status_code == 200
    assert "свободная неделя" in response.text
    # Карточек занятий нет: серверный блок — `class="cal-event"` или
    # `class="cal-event cal-event--past"`; классы `cal-event__*` из
    # inert-шаблона рендерера карточек карточками не считаются.
    assert not re.search(r'class="cal-event[\s"]', response.text)


def test_calendar_past_events_dimmed(client, calendar_owner, student_factory):
    """Прошедшие уроки приглушены классом cal-event--past."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Иван")
    # Неделя 12–18 октября 2026 целиком в прошлом (тесты пишутся позже).
    _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 14, 14, 0),
    )
    past = client.get("/tutor/calendar?start=2026-10-12")
    assert "cal-event--past" in past.text
    # Урок далеко в будущем — не «прошедший».
    future_lesson = student_factory(tutor_id=calendar_owner, first_name="Пётр")
    _insert_lesson(
        calendar_owner, student_id=future_lesson,
        starts_at=datetime(2099, 2, 3, 10, 0),
    )
    future = client.get("/tutor/calendar?start=2099-02-02")
    assert 'data-lesson-id="' in future.text  # уроки есть
    assert "cal-event--past" not in future.text


# --------------------------------------------------------------------------
# 3.4 Ассеты и ссылки: только локальные, без заглушек на несуществующее
# --------------------------------------------------------------------------

def test_calendar_page_has_no_broken_route_links(client):
    """Область страницы календаря не ссылается на несуществующие маршруты.

    Проверяется только `<main>` — собственная разметка календаря; ссылки
    сайдбара переводятся на `/tutor/*` отдельной задачей раздела 6.
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    main = re.search(r"<main class=\"main\">(.*?)</main>", response.text, re.S)
    assert main, "На странице нет <main> с областью календаря"
    for route in (
        "/bookings", "/tasks", "/lessons", "/finance", "/stats",
        "/mailings", "/groups", "/changelog", "/settings", "/profile",
    ):
        assert f'href="{route}"' not in main.group(1), route
        assert f'action="{route}"' not in main.group(1), route


def test_calendar_page_uses_only_local_assets(client):
    """Календарь подключает только локальные ассеты, без CDN-скриптов."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "/static/styles.css" in response.text
    # Все скрипты страницы — локальные (конвенция проекта, как в test_index).
    script_sources = re.findall(r'<script[^>]*\ssrc="([^"]+)"', response.text)
    assert script_sources
    assert all(src.startswith("/static/") for src in script_sources), script_sources
    # В собственной области календаря нет внешних URL (CDN и прочего).
    main = re.search(r"<main class=\"main\">(.*?)</main>", response.text, re.S)
    assert main
    assert "http://" not in main.group(1)
    assert "https://" not in main.group(1)


# --------------------------------------------------------------------------
# 4.1 HTMX-листание недель: фрагмент вместо полной страницы
# --------------------------------------------------------------------------

_HTMX = {"HX-Request": "true"}


def test_calendar_htmx_fragment_only(client):
    """HX-Request → только область календаря: без <html> и без сайдбара."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12", headers=_HTMX)
    assert response.status_code == 200
    assert "<html" not in response.text
    assert 'class="sidebar"' not in response.text
    assert 'id="calendar-swap"' not in response.text  # сама область не заворачивается
    assert "cal-toolbar" in response.text  # панель на месте
    assert "12 октября – 18 октября 2026" in response.text


def test_calendar_week_buttons_use_hx_get(client):
    """Кнопки недель и «Сегодня» листают через hx-get с hx-target на область.

    В адресе несётся активный режим раскраски (`?color=`), чтобы выбор не
    терялся на первом же клике (design.md D5).
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert 'hx-get="/tutor/calendar?start=2026-10-05&color=target"' in response.text  # назад
    assert 'hx-get="/tutor/calendar?start=2026-10-19&color=target"' in response.text  # вперёд
    assert 'hx-get="/tutor/calendar?color=target"' in response.text  # «Сегодня»
    assert response.text.count('hx-target="#calendar-swap"') >= 3

    # В режиме «По статусу» параметр меняется вместе с раскраской.
    status = client.get("/tutor/calendar?start=2026-10-12&color=status")
    assert 'hx-get="/tutor/calendar?start=2026-10-19&color=status"' in status.text


def test_calendar_invalid_start_falls_to_current_week(client):
    """`?start=banana` → текущая неделя, без 4xx."""
    _login(client)
    bad = client.get("/tutor/calendar?start=banana", headers=_HTMX)
    assert bad.status_code == 200
    current = client.get("/tutor/calendar", headers=_HTMX)
    # Заголовок кривого запроса совпадает с заголовком текущей недели.
    title = re.search(r'cal-toolbar__title">\s*(.*?)\s*<', current.text)
    assert title, "В фрагменте нет заголовка диапазона"
    assert title.group(1) in bad.text


def test_calendar_specific_week_start(client):
    """`?start=2026-10-12` → заголовок недели с 12 октября."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12", headers=_HTMX)
    assert "12 октября – 18 октября 2026" in response.text


# --------------------------------------------------------------------------
# 4.2 Навигация: подмена только области, содержимое недели меняется
# --------------------------------------------------------------------------

def test_calendar_navigation_changes_week_content(client):
    """Фрагмент следующей недели содержит её заголовок, а не текущий."""
    _login(client)
    current = client.get("/tutor/calendar", headers=_HTMX)
    current_title = re.search(r'cal-toolbar__title">\s*(.*?)\s*<', current.text)
    assert current_title
    next_week = client.get("/tutor/calendar?start=2026-10-19", headers=_HTMX)
    assert next_week.status_code == 200
    assert "19 октября – 25 октября 2026" in next_week.text
    assert 'id="calendar-swap"' not in next_week.text


def test_calendar_full_page_still_renders_after_fragment(client):
    """Полная страница (без HX-Request) по-прежнему отдаёт каркас со сайдбаром."""
    _login(client)
    page = client.get("/tutor/calendar?start=2026-10-12")
    assert page.status_code == 200
    assert 'id="calendar-swap"' in page.text
    assert 'class="sidebar"' in page.text


# --------------------------------------------------------------------------
# 5.1 Клиентский слой: calendar.js и данные четвертей часа
# --------------------------------------------------------------------------

def test_calendar_loads_calendar_js_before_alpine(client):
    """calendar.js — локальный defer-скрипт до alpine.min.js (alpine:init).

    Компонент подписывается на `alpine:init`, а defer-скрипты выполняются
    в порядке документа — позже Alpine регистрация не успевает сработать.
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert '<script src="/static/calendar.js" defer></script>' in response.text
    assert (
        response.text.index("/static/calendar.js")
        < response.text.index("/static/alpine.min.js")
    )
    # Точка монтирования: Alpine-компонент на корне области подмены.
    assert 'x-data="calendarGrid"' in response.text


def test_calendar_slots_expose_quarter_data(client):
    """Ячейки четвертей несут data-start/data-end — hover и клик по ним."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert 'data-start="2026-10-12T06:00"' in response.text
    assert 'data-end="2026-10-12T06:15"' in response.text
    assert 'data-start="2026-10-14T07:15"' in response.text  # среда
    assert 'data-start="2026-10-18T22:45"' in response.text  # последняя четверть


# --------------------------------------------------------------------------
# 5.2 Модалка «Новый урок»: поля и точки входа
# --------------------------------------------------------------------------

def test_calendar_wires_lessons_js_and_modal_container(client):
    """3.2: lessons.js до alpine.min.js, `#modal` вне области свопа.

    Форма урока живёт в контейнере `#modal`, который htmx не подменяет
    при листании недель (design.md D6): иначе открытая модалка исчезала
    бы вместе с областью `#calendar-swap`.
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert '<script src="/static/lessons.js" defer></script>' in response.text
    assert (
        response.text.index("/static/calendar.js")
        < response.text.index("/static/lessons.js")
        < response.text.index("/static/alpine.min.js")
    )
    # Контейнер модалки есть и находится вне области подмены.
    swap = re.search(
        r'<div id="calendar-swap".*?</section>', response.text, re.S
    )
    assert swap, "Область #calendar-swap не найдена"
    assert 'id="modal"' not in swap.group(0)
    assert '<div id="modal"></div>' in response.text

def test_calendar_lesson_card_opens_edit_form(client, calendar_owner, student_factory):
    """3.3: карточка урока несёт edit-ссылку в #modal, карточка отпуска — нет."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Иван")
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 14, 14, 0),
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    card = _card(response.text, lesson_id)
    assert card, "Карточки урока нет в сетке"
    assert f'hx-get="/tutor/lessons/{lesson_id}/edit"' in card
    assert 'hx-target="#modal"' in card
    assert 'hx-swap="innerHTML"' in card

    # Август: демо-отпуск — блок без id урока и без edit-ссылки.
    august = client.get("/tutor/calendar?start=2026-08-03")
    vacation = re.search(r'<div class="cal-vacation">', august.text)
    assert vacation, "Блока отпуска нет в сетке"
    assert "/edit" not in august.text


def test_calendar_entry_points_open_lesson_form(client):
    """3.4: клик по четверти и «Добавить» открывают форму создания урока.

    Обе точки входа ведут на `GET /tutor/lessons/new` с префиллом
    `starts_at` (design.md D9): четверть — своя дата/время, кнопка —
    ближайшая будущая четверть (`prefillMoment`).
    """
    _login(client)
    page = client.get("/tutor/calendar?start=2026-10-12")
    # Адрес формы — в разметке корня (JS читает data-lesson-new).
    assert 'data-lesson-new="/tutor/lessons/new"' in page.text
    # «Добавить» и FAB по-прежнему открывают форму (обработчик openForm).
    assert 'id="cal-add" @click="openForm()"' in page.text
    assert 'class="cal-fab" type="button" @click="openForm()"' in page.text

    js = _calendar_js()
    # Клик по четверти: своя дата/время четверти в форме создания.
    slot_open = js[js.index("openSlot: function"):js.index("openLessonForm: function")]
    assert "openLessonForm(data.date, data.time)" in slot_open
    # Кнопка «Добавить»: ближайшая будущая четверть из prefillMoment.
    form_open = js[js.index("openForm: function"):js.index("toggleMore: function")]
    assert "prefillMoment()" in form_open
    assert "openLessonForm(moment.date, moment.time)" in form_open
    # Сама форма запрашивается htmx-ом в #modal с параметром префилла.
    helper = js[js.index("openLessonForm: function"):js.index("prefillMoment: function")]
    assert 'htmx.ajax("GET", url + "?starts_at="' in helper
    assert 'target: "#modal"' in helper


def test_calendar_refreshes_week_after_lesson_saved(client):
    """3.5: `lesson-saved` перерисовывает неделю с текущим `start`.

    Подписка живёт на `#calendar-swap` (design.md D6): после сохранения
    формы календарь перезапрашивает ту же неделю, а не первую открытую —
    корень не подменяется, поэтому calendar.js переводит его hx-get на
    видимую неделю (`syncWeekParam`).
    """
    _login(client)
    page = client.get("/tutor/calendar?start=2026-10-19")
    swap = re.search(
        r'<div id="calendar-swap".*?>', page.text, re.S
    )
    assert swap, "Область #calendar-swap не найдена"
    tag = swap.group(0)
    assert 'hx-get="/tutor/calendar?start=2026-10-19&color=target"' in tag
    assert 'hx-trigger="lesson-saved from:body"' in tag
    assert 'hx-target="#calendar-swap"' in tag

    js = _calendar_js()
    assert "syncWeekParam" in js
    # Адрес перерисовки собирается из видимой недели и активного режима.
    assert "this.withColor(this.weekPath())" in js
    # Подписка на подмену области — у постоянного корня.
    assert 'root.addEventListener("htmx:afterSwap"' in js


def test_calendar_demo_lesson_modal_removed(client):
    """3.6: демо-модалка урока удалена — урок создаётся формой страницы Уроков.

    Остаются демо-слот и отпуск: их спеки в change не входят
    (design.md D9), `openSlot`/`createSlot`/`createVacation` работают.
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    text = response.text
    # Демо-выбора ученика и «Сохранить» в календаре больше нет.
    assert 'id="cal-student"' not in text
    assert "cal-student-field" not in text
    assert "saveLesson" not in text
    assert "demo_students" not in text
    # Слот и отпуск на месте.
    assert 'id="cal-slot-date"' in text
    assert '@click="createSlot()">Создать</button>' in text
    assert 'id="cal-vacation-form"' in text

    js = _calendar_js()
    assert "saveLesson" not in js
    assert "createSlot" in js
    assert "createVacation" in js
    # Слоты/отпуск остались DOM-only: сетевых запросов в calendar.js нет.
    assert "fetch(" not in js
    assert "XMLHttpRequest" not in js


def test_calendar_modal_entry_points_wired(client):
    """Точки входа: клик четверти, «Добавить», мобильная FAB.

    Все три ведут на форму создания урока (`openLessonForm`), а рендерер
    `#cal-event-template` обслуживает демо-слоты.
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert '@click="openSlot($event.currentTarget)"' in response.text
    assert 'id="cal-add" @click="openForm()"' in response.text
    assert 'class="cal-fab" type="button" @click="openForm()"' in response.text
    assert 'id="cal-event-template"' in response.text


# --------------------------------------------------------------------------
# 5.3 Drag: данные карточек для Pointer Events
# --------------------------------------------------------------------------

def test_calendar_events_expose_drag_data(client, calendar_owner, student_factory):
    """Карточки уроков несут дату колонки, начало и длительность в минутах.

    Драг в calendar.js читает эти значения и фиксирует новый слот только
    в DOM — без сетевых запросов. Значения: Иван И. в понедельник
    10:00 на 40 минут.
    """
    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Иван", last_name="Иванов"
    )
    _insert_lesson(
        calendar_owner,
        student_id=student_id,
        starts_at=datetime(2026, 10, 12, 10, 0),
        duration_min=40,
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    card = re.search(
        r'<div class="cal-event[^"]*"(?:(?!</div>).)*?data-student="Иван И\.[^"]*"'
        r'(?:(?!</div>).)*?</div>',
        response.text,
        re.S,
    )
    assert card, "У карточки урока нет данных для drag"
    # Значения для drag: дата колонки, начало и длительность в минутах.
    for marker in (
        'data-lesson-id="',
        'data-target-id="',
        'data-date="2026-10-12"',
        'data-start-min="600"',
        'data-duration-min="40"',
    ):
        assert marker in card.group(0), marker
    # Тач-сценарий drag не конфликтует со скроллом (styles.css).
    css = (Path(__file__).resolve().parent.parent / "app" / "static" / "styles.css").read_text(
        encoding="utf-8"
    )
    assert "touch-action: none" in css
    assert ".cal-event--dragging" in css
    assert ".cal-slot--drop" in css
    # Слушатели Pointer Events подключены компонентом.
    assert "setPointerCapture" in (
        Path(__file__).resolve().parent.parent / "app" / "static" / "calendar.js"
    ).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 5.4 Кнопки-заглушки: селекторы есть, битых ссылок нет
# --------------------------------------------------------------------------

def test_calendar_stub_buttons_without_broken_links(client):
    """«Ссылка на окна» и «Цвет: ученик»: селекторы на месте, битых нет."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    main = re.search(r"<main class=\"main\">(.*?)</main>", response.text, re.S)
    assert main, "На странице нет <main>"
    area = main.group(1)

    # Селекторы кнопок и их обработчики-заглушки.
    assert 'id="cal-link"' in area
    assert '@click="copyWeekLink()"' in area
    assert 'id="cal-color"' in area
    assert "colorOpen" in area              # выпадающий список кнопки цвета
    assert 'class="cal-toast"' in area      # тост подтверждения «демо»

    # У самих кнопок нет href/action — вести они могут только на JS-заглушку.
    for button in re.findall(r'<button[^>]*id="cal-(?:link|color)"[^>]*>', area):
        assert "href=" not in button, button
        assert "action=" not in button, button

    # JS-заглушки: копирование ссылки через clipboard и тост «демо».
    js = (Path(__file__).resolve().parent.parent / "app" / "static" / "calendar.js").read_text(
        encoding="utf-8"
    )
    assert "clipboard.writeText" in js
    assert "Демо" in js
    # Ссылка недели строится из текущей сетки, а не из устаревших data-*.
    assert ".cal-day[data-date]" in js



def test_demo_week_start_normalizes_to_monday():
    """`?start=` любой день недели → понедельник; строка ISO тоже работает."""
    assert week_start(date(2026, 10, 12)) == date(2026, 10, 12)  # уже понедельник
    assert week_start(date(2026, 10, 15)) == date(2026, 10, 12)  # четверг
    assert week_start(date(2026, 10, 18)) == date(2026, 10, 12)  # воскресенье
    assert week_start("2026-10-14") == date(2026, 10, 12)  # строка ?start=


def test_demo_build_week_normalizes_any_day_of_week():
    """`build_week` принимает любой день недели и строит 7 дней от понедельника."""
    days = build_week(date(2026, 10, 15))  # четверг запрошенной недели
    assert len(days) == 7
    assert [d.date.weekday() for d in days] == list(range(7))
    assert days[0].date == date(2026, 10, 12)


def test_demo_determinism_same_week_identical():
    """Два вызова одной недели идентичны (листание стабильно)."""
    assert build_week(_PLAIN_MONDAY) == build_week(_PLAIN_MONDAY)
    # и в середине недели, и на строке — тот же результат
    assert build_week(date(2026, 10, 14)) == build_week("2026-10-12")


def test_demo_vacation_on_demo_week():
    """Август — демо-отпуск: заглушка «Отпуск» вместо занятий."""
    days = build_week(date(2026, 8, 3))  # понедельник демо-недели отпуска
    events = [event for day in days for event in day.events]
    assert events  # отпуск присутствует
    assert all(event.kind == VACATION for event in events)
    assert not any(day.lessons for day in days)


def test_demo_between_terms_week_is_empty():
    """Новогодний перерыв — неделя вообще без событий (пустое состояние)."""
    days = build_week(date(2026, 12, 28))
    assert all(not day.events for day in days)
    # соседние недели «пустыми» не считаются
    assert not is_between_terms(date(2026, 12, 21))
    assert not is_between_terms(date(2026, 1, 12))


def test_demo_lessons_word_declension():
    """Склонения числа занятий: 1 урок / 2 урока / 5 уроков / 21 урок…"""
    assert lessons_word(1) == "1 урок"
    assert lessons_word(2) == "2 урока"
    assert lessons_word(3) == "3 урока"
    assert lessons_word(4) == "4 урока"
    assert lessons_word(5) == "5 уроков"
    assert lessons_word(11) == "11 уроков"
    assert lessons_word(12) == "12 уроков"
    assert lessons_word(21) == "21 урок"
    assert lessons_word(22) == "22 урока"


# --------------------------------------------------------------------------
# 6. Слоты (спека slot-booking, change add-slot-booking): диалог создания,
#    карточка в сетке, диалог записи — SSR-разметка и статические проверки
# --------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"


def _calendar_js() -> str:
    """Содержимое calendar.js для статических проверок спеки."""
    return (_STATIC_DIR / "calendar.js").read_text(encoding="utf-8")


def _styles_css() -> str:
    """Содержимое styles.css для статических проверок спеки."""
    return (_STATIC_DIR / "styles.css").read_text(encoding="utf-8")


def test_calendar_slot_dialog_markup(client):
    """Задача 1.1: кнопка «Добавить слот», поля даты/времени, «Создать».

    Диалог содержит только поля слота: выбор ученика удалён вместе с
    демо-модалкой урока (design.md D9).
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert 'id="cal-add-slot" @click="openSlotDialog()"' in response.text
    assert "Добавить слот" in response.text
    assert "Новый слот" in response.text
    # Редактируемые дата и время: шаг 900 с = граница четверти часа.
    date_input = re.search(r'id="cal-slot-date"[^>]*', response.text)
    assert date_input, "Поля даты слота нет в разметке"
    assert 'type="date"' in date_input.group(0)
    time_input = re.search(r'id="cal-slot-time"[^>]*', response.text)
    assert time_input, "Поля времени слота нет в разметке"
    assert 'type="time"' in time_input.group(0)
    assert 'step="900"' in time_input.group(0)
    # Кнопка «Создать» вызывает createSlot.
    assert '@click="createSlot()">Создать</button>' in response.text
    # Поля выбора ученика в диалоге нет — урок создаётся формой Уроков.
    assert "cal-student-field" not in response.text
    assert 'id="cal-student"' not in response.text


def test_calendar_slot_creation_static():
    """Задача 1.2: openSlotDialog/createSlot/snapToQuarter, без сети.

    Слот создаётся только в DOM — ни fetch, ни XMLHttpRequest в calendar.js
    нет вообще (спека «DOM-only жизненный цикл»).
    """
    js = _calendar_js()
    assert "openSlotDialog" in js
    assert "createSlot" in js
    assert "snapToQuarter" in js
    # Создание слота не обращается к серверу.
    assert "fetch(" not in js
    assert "XMLHttpRequest" not in js


def test_calendar_slot_card_renderer_static():
    """Задача 2.1: единый рендерер с kind — подпись и классы слота.

    Карточка слота: класс cal-event--slot, подпись «Свободен · запись по
    ссылке»; после записи — cal-event--booked и подпись «Занят: <имя>»
    (спека slot-booking).
    """
    js = _calendar_js()
    assert "Свободен · запись по ссылке" in js
    assert "cal-event--slot" in js
    assert "cal-event--booked" in js
    # Карточка слота создаётся через renderCard с kind: "slot".
    assert 'kind: "slot"' in js
    # Кнопка «Записаться» создаётся только для свободного слота.
    assert 'book.textContent = "Записаться"' in js
    # Подпись занятого слота.
    assert '"Занят: "' in js


def test_calendar_slot_styles_static():
    """Задача 2.2: стили слота — пунктирная рамка, классы свободен/занят.

    Светлая и тёмная темы заданы переменной --cal-slot-accent (токены
    в :root и .dark), поэтому компонентные правила тему не дублируют.
    """
    css = _styles_css()
    assert ".cal-event--slot" in css
    assert ".cal-event--booked" in css
    slot_block = re.search(r"\.cal-event--slot\s*\{(.*?)\}", css, re.S)
    assert slot_block, "Блока .cal-event--slot нет в styles.css"
    assert "border-style: dashed" in slot_block.group(1)
    # Собственный цвет слота — на переменных обеих тем.
    assert "--cal-slot-accent" in css
    root_block = re.search(r":root\s*\{(.*?)\n  \}", css, re.S)
    dark_block = re.search(r"\.dark\s*\{(.*?)\n  \}", css, re.S)
    assert root_block and "--cal-slot-accent" in root_block.group(1)
    assert dark_block and "--cal-slot-accent" in dark_block.group(1)


def test_calendar_slot_state_is_not_clipped():
    """Подпись состояния слота не сжимается в коротком слоте.

    Регрессия после правки карточки урока: `.cal-event` — flex-колонка,
    и подпись «Свободен · запись по ссылке» схлопывалась до нулевой
    высоты — на слоте оставалось одно время и кнопка. Строка состояния
    объявлена `flex: 0 0 auto`, а интервал времени скрывается контейнерным
    запросом, когда трёх строк не помещается.
    """
    css = _styles_css()

    state = re.search(r"\.cal-event__state\s*\{([^}]*)\}", css)
    assert state, "В styles.css нет правила .cal-event__state"
    assert "flex: 0 0 auto" in state.group(1), "Подпись состояния не должна сжиматься"

    slot_container = re.search(
        r"@container \(max-height: \d+px\)\s*\{\s*"
        r"\.cal-event--slot \.cal-event__meta\s*\{[^}]*display:\s*none",
        css,
    )
    assert slot_container, (
        "Нет @container-правила, скрывающего время слота в короткой карточке"
    )


def test_calendar_booking_dialog_markup(client):
    """Задача 3.1: диалог «Запись на слот» — два обязательных поля и кнопки."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "Запись на слот" in response.text
    # Обязательные поля «Имя» и «Телефон/Telegram» (нативная валидация).
    name_input = re.search(r'id="cal-book-name"[^>]*', response.text)
    assert name_input, "Поля «Имя» нет в разметке"
    assert "required" in name_input.group(0)
    assert "Имя" in response.text
    contact_input = re.search(r'id="cal-book-contact"[^>]*', response.text)
    assert contact_input, "Поля «Телефон/Telegram» нет в разметке"
    assert "required" in contact_input.group(0)
    assert "Телефон/Telegram" in response.text
    # Кнопки «Отмена» и «Записаться» (submit у формы записи).
    assert '@click="closeBooking()">Отмена</button>' in response.text
    assert ">Записаться</button>" in response.text
    assert "confirmBooking($event)" in response.text


def test_calendar_booking_js_static():
    """Задача 3.2: openBooking/confirmBooking/data-booked-by в calendar.js.

    Открытие — только от свободной карточки слота, подтверждение пишет
    данные в DOM-атрибуты карточки (design.md D4), без сетевых запросов.
    """
    js = _calendar_js()
    assert "openBooking" in js
    assert "confirmBooking" in js
    assert "data-booked-by" in js
    # Открытый диалог ведёт на DOM-узел карточки, а не на индекс.
    assert "_bookingSlot" in js


def test_calendar_booking_contact_in_title_static():
    """Задача 3.3: контакт из формы попадает в title занятой карточки.

    Данные записи живут только в DOM-атрибутах (data-contact/title) — без
    БД, localStorage и сетевых запросов. Проверка сужена до блока записи:
    localStorage в файле есть, но он хранит режим раскраски (design.md D5).
    """
    js = _calendar_js()
    assert 'card.setAttribute("title"' in js
    assert 'card.setAttribute("data-contact"' in js
    booking = js[js.index("openBooking: function"):js.index("closeBooking: function")]
    assert "localStorage" not in booking


def test_calendar_slot_excluded_from_drag_static():
    """Задача 2.3: в ветке начала драга есть исключение .cal-event--slot.

    Позиционирование слота переиспользует логику наложения карточек —
    layoutDay применяет ту же кластеризацию, что services/presentation.py
    (слот поверх занятия: видны обе).
    """
    js = _calendar_js()
    start = js.index("onEventPointerDown")
    end = js.index("onDragMove")
    assert ".cal-event--slot" in js[start:end]
    # Раскладка наложения карточек вызывается при создании слота.
    assert "layoutDay" in js
    assert "this.layoutDay(day)" in js


# --------------------------------------------------------------------------
# 7. Отпуск (спека vacation-creation, change add-vacation-dialog): меню ⋮ в
#    панели, диалог «Новый отпуск», клик по отпуску — SSR-разметка и
#    статические проверки (design.md D6: без запуска JS)
# --------------------------------------------------------------------------

def test_calendar_more_menu_markup(client):
    """Задача 1.1: #cal-more сразу после #cal-add, пункты внутри меню.

    Прямая кнопка слота из панели переехала в меню: id и обработчик
    сохранены, поэтому существующий test_calendar_slot_dialog_markup
    проходит без правок.
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    text = response.text

    # Кнопка ⋮ идёт в разметке сразу после «Добавить».
    assert re.search(
        r'id="cal-add"[^>]*>Добавить</button>\s*'
        r'<div class="cal-more">\s*<button[^>]*id="cal-more"',
        text,
    ), "Кнопки #cal-more нет сразу после #cal-add"
    more_button = re.search(r"<button[^>]*id=\"cal-more\"[^>]*>", text)
    assert more_button, "Кнопки #cal-more нет в разметке"
    assert 'aria-haspopup="true"' in more_button.group(0)
    assert ':aria-expanded' in more_button.group(0)

    # Оба пункта — внутри #cal-more-menu, атрибуты закрытия на месте.
    menu = re.search(r'<ul[^>]*id="cal-more-menu"[^>]*>.*?</ul>', text, re.S)
    assert menu, "Выпадающего меню #cal-more-menu нет в разметке"
    items = menu.group(0)
    assert 'id="cal-add-slot" @click="openSlotDialog()"' in items
    assert 'id="cal-add-vacation" @click="openVacationDialog()"' in items
    assert '@click.outside="closeMore()"' in items
    assert '@keydown.escape.window="closeMore()"' in items

    # Прямая кнопка слота из панели удалена: id встречается ровно один
    # раз — в меню; точка входа слота в разметке тоже ровно одна.
    assert text.count('id="cal-add-slot"') == 1
    assert text.count("openSlotDialog()") == 1


def test_calendar_more_menu_js_static():
    """Задача 1.2: moreOpen/toggleMore/closeMore, выбор пункта закрывает меню."""
    js = _calendar_js()
    assert "moreOpen" in js
    assert "toggleMore" in js
    assert "closeMore" in js
    # Оба пункта закрывают меню перед открытием диалога.
    slot_open = js[js.index("openSlotDialog: function"):js.index("closeModal: function")]
    assert "closeMore()" in slot_open
    vac_open = js[js.index("openVacationDialog: function"):js.index("closeVacation: function")]
    assert "closeMore()" in vac_open


def test_calendar_vacation_dialog_markup(client):
    """Задача 2.1: диалог «Новый отпуск» — два обязательных датовых поля.

    Диапазон защищён нативной валидацией: `:min` у конца привязан к
    началу (design.md D3), отправка формы вызывает createVacation.
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    text = response.text
    assert "Новый отпуск" in text
    assert 'id="cal-vacation-form"' in text
    assert "createVacation($event)" in text

    start = re.search(r'id="vac-start"[^>]*', text)
    assert start, "Поля начала отпуска нет в разметке"
    assert 'type="date"' in start.group(0)
    assert "required" in start.group(0)

    end = re.search(r'id="vac-end"[^>]*', text)
    assert end, "Поля конца отпуска нет в разметке"
    assert 'type="date"' in end.group(0)
    assert "required" in end.group(0)
    assert ':min="vacationForm.start"' in end.group(0)

    assert '@click="closeVacation()">Отмена</button>' in text
    assert re.search(r'<button[^>]*type="submit">Создать</button>', text)


def test_calendar_vacation_create_static():
    """Задача 2.2: createVacation и префиллы в calendar.js, без сети.

    Отпуск создаётся только в DOM: ни fetch, ни XMLHttpRequest в
    calendar.js нет вообще (спека «DOM-only жизненный цикл»).
    """
    js = _calendar_js()
    for token in (
        "createVacation",
        "vacationForm",
        "openVacationDialog",
        "prefillMoment",
        '"cal-vacation"',
    ):
        assert token in js, token
    # Блок вставляется первым ребёнком дня (под карточки), диапазон
    # защищён defensive-проверкой end < start.
    assert "insertBefore" in js
    assert "end < start" in js
    assert "fetch(" not in js
    assert "XMLHttpRequest" not in js


def test_calendar_vacation_click_guard_static():
    """Задача 3.1: в теле openSlot есть проверка .cal-vacation.

    Guard покрывает и клиентские блоки отпуска, и серверную демо-заглушку —
    клик по дню с отпуском не открывает форму урока (спека vacation-creation).
    """
    js = _calendar_js()
    body = js[js.index("openSlot: function"):js.index("prefillMoment: function")]
    assert '".cal-vacation"' in body


# --------------------------------------------------------------------------
# 8. Реальные уроки недели (change calendar-real-lessons, раздел 2):
#    недельная выборка, событие из строки БД, сетка, наложение, «просрочен»,
#    шапка дня и пустое состояние
# --------------------------------------------------------------------------

def _card(response_text: str, lesson_id: str) -> str:
    """Разметка карточки урока по её data-lesson-id (пустая строка — нет)."""
    match = re.search(
        r'<div class="cal-event[^"]*"(?:(?!</div>).)*?'
        rf'data-lesson-id="{re.escape(lesson_id)}".*?</div>',
        response_text,
        re.S,
    )
    return match.group(0) if match else ""


def test_week_lessons_returns_only_own_lessons_of_week(calendar_owner, student_factory):
    """2.1: выборка отдаёт уроки только этого репетитора и только недели."""
    from app.calendar.services.week import week_lessons
    from app.database import SessionLocal

    own = student_factory(tutor_id=calendar_owner, first_name="Свой")
    in_week = _insert_lesson(
        calendar_owner, student_id=own, starts_at=datetime(2026, 10, 14, 14, 0)
    )
    # Свой, но другая неделя.
    _insert_lesson(
        calendar_owner, student_id=own, starts_at=datetime(2026, 10, 21, 14, 0)
    )
    # Чужой репетитор, та же неделя.
    with SessionLocal() as db:
        from app.tutor.models.tutor import Tutor

        stranger = Tutor(
            name="Чужой",
            email="stranger-week@example.com",
            password_hash="pbkdf2_sha256$1$placeholder$placeholder",
        )
        db.add(stranger)
        db.commit()
        stranger_id = stranger.id
    stranger_student = student_factory(tutor_id=stranger_id, first_name="Чужой")
    _insert_lesson(
        stranger_id, student_id=stranger_student,
        starts_at=datetime(2026, 10, 14, 15, 0),
    )

    with SessionLocal() as db:
        rows = week_lessons(db, calendar_owner, date(2026, 10, 12))

    assert [row.lesson.id for row in rows] == [in_week]
    assert rows[0].target_name == "Свой"


def test_week_lessons_window_is_start_based(calendar_owner, student_factory):
    """2.1: окно `[monday, monday+7)` — воскресенье 23:50 в чужую неделю не попадает."""
    from app.calendar.services.week import week_lessons
    from app.database import SessionLocal

    student_id = student_factory(tutor_id=calendar_owner, first_name="Граница")
    # Воскресенье 18.10 23:50 — ещё неделя 12.10.
    sunday = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 18, 23, 50),
    )
    # Понедельник 19.10 00:00 — уже следующая неделя.
    monday = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 19, 0, 0),
    )

    with SessionLocal() as db:
        first = week_lessons(db, calendar_owner, date(2026, 10, 12))
        second = week_lessons(db, calendar_owner, date(2026, 10, 19))

    assert [row.lesson.id for row in first] == [sunday]
    assert [row.lesson.id for row in second] == [monday]


def test_week_lessons_group_target(calendar_owner, group_factory):
    """2.1: у группового урока цель — группа, её имя, id и цвет."""
    from app.calendar.services.week import week_lessons
    from app.common.colors import PALETTE
    from app.database import SessionLocal

    group_id = group_factory(
        tutor_id=calendar_owner, name="Группа 8Б", color=PALETTE[3]
    )
    lesson_id = _insert_lesson(
        calendar_owner, student_id=None, group_id=group_id, type="group",
        starts_at=datetime(2026, 10, 14, 16, 0),
    )

    with SessionLocal() as db:
        rows = week_lessons(db, calendar_owner, date(2026, 10, 12))

    row = next(row for row in rows if row.lesson.id == lesson_id)
    assert row.target_name == "Группа 8Б"
    assert row.target_id == group_id
    assert row.target_color == PALETTE[3]


def test_schedule_event_from_lesson_carries_id_status_color(calendar_owner, student_factory):
    """2.2: событие из строки БД несёт id урока, цель, статус и цвет."""
    from app.calendar.services.schedule_event import ScheduleEvent
    from app.common.colors import PALETTE
    from app.database import SessionLocal
    from app.lesson.models.lesson import Lesson

    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Мария", color=PALETTE[6]
    )
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id, price=1500,
        starts_at=datetime(2026, 10, 14, 14, 0), duration_min=50,
    )

    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        event = ScheduleEvent.from_lesson(
            lesson,
            target_name="Мария С.",
            target_id=student_id,
            target_color=PALETTE[6],
        )

    assert event.lesson_id == lesson_id
    assert event.status == "planned"
    assert event.is_completed is False
    assert event.target_id == student_id
    assert event.student == "Мария С."
    assert event.color == PALETTE[6]
    assert event.price == 1500
    assert (event.day, event.start, event.end) == (
        date(2026, 10, 14), time(14, 0), time(14, 50)
    )


def test_calendar_grid_contains_real_lessons_with_lesson_id(
    client, calendar_owner, student_factory
):
    """2.3: сетка недели содержит реальные уроки с data-lesson-id."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Иван")
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 14, 14, 0),
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    card = _card(response.text, lesson_id)
    assert card, "Реального урока нет в сетке"
    assert f'data-lesson-id="{lesson_id}"' in card


def test_calendar_isolates_tutor_lessons(client, calendar_owner, student_factory):
    """2.3: уроки другого репетитора в календарь не попадают."""
    from app.database import SessionLocal
    from app.tutor.models.tutor import Tutor

    with SessionLocal() as db:
        stranger = Tutor(
            name="Чужой",
            email="stranger-grid@example.com",
            password_hash="pbkdf2_sha256$1$placeholder$placeholder",
        )
        db.add(stranger)
        db.commit()
        stranger_id = stranger.id

    stranger_student = student_factory(tutor_id=stranger_id, first_name="Чужой")
    foreign_lesson = _insert_lesson(
        stranger_id, student_id=stranger_student,
        starts_at=datetime(2026, 10, 14, 15, 0),
    )

    response = client.get("/tutor/calendar?start=2026-10-12")
    assert foreign_lesson not in response.text
    assert "Чужой" not in response.text


def test_calendar_keeps_demo_vacation_with_real_lessons(
    client, calendar_owner, student_factory
):
    """2.3: демо-отпуск остаётся источником и сосуществует с уроками БД."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Иван")
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 8, 5, 10, 0),
    )
    response = client.get("/tutor/calendar?start=2026-08-03")
    assert "Отпуск" in response.text
    assert _card(response.text, lesson_id)


def test_calendar_layout_overlaps_real_lessons(client, calendar_owner, student_factory):
    """2.4: layout_events накладывает пересекающиеся реальные уроки."""
    first = student_factory(tutor_id=calendar_owner, first_name="Иван")
    second = student_factory(tutor_id=calendar_owner, first_name="Ольга")
    first_id = _insert_lesson(
        calendar_owner, student_id=first,
        starts_at=datetime(2026, 10, 14, 14, 0), duration_min=40,
    )
    second_id = _insert_lesson(
        calendar_owner, student_id=second,
        starts_at=datetime(2026, 10, 14, 14, 20), duration_min=40,
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    first_card, second_card = _card(response.text, first_id), _card(response.text, second_id)
    assert "--left: 0%" in first_card and "--width: 50%" in first_card
    assert "--left: 50%" in second_card and "--width: 50%" in second_card


def test_calendar_real_past_lesson_dimmed(client, calendar_owner, student_factory):
    """2.4: прошедший реальный урок приглушён, будущий — нет."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Прошлый")
    past_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2020, 1, 8, 10, 0),
    )
    future_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 3, 10, 0),
    )
    past = client.get("/tutor/calendar?start=2020-01-06")
    future = client.get("/tutor/calendar?start=2099-02-02")
    assert "cal-event--past" in _card(past.text, past_id)
    assert "cal-event--past" not in _card(future.text, future_id)


def test_is_overdue_only_for_planned_past_lessons():
    """2.5: «просрочен» — запланированный урок, чьё время уже прошло."""
    from app.calendar.services.presentation import is_overdue
    from app.calendar.services.schedule_event import ScheduleEvent

    now = datetime(2026, 10, 21, 12, 0)
    planned_past = ScheduleEvent(
        day=date(2026, 10, 21), start=time(10, 0), end=time(10, 40),
        lesson_id="a", status="planned",
    )
    planned_future = ScheduleEvent(
        day=date(2026, 10, 21), start=time(13, 0), end=time(13, 40),
        lesson_id="b", status="planned",
    )
    completed_past = ScheduleEvent(
        day=date(2026, 10, 21), start=time(10, 0), end=time(10, 40),
        lesson_id="c", status="completed", is_completed=True,
    )
    vacation = ScheduleEvent(day=date(2026, 10, 21), start=time(0, 0), end=time(23, 59), kind=VACATION)

    assert is_overdue(planned_past, now=now) is True
    assert is_overdue(planned_future, now=now) is False
    assert is_overdue(completed_past, now=now) is False
    assert is_overdue(vacation, now=now) is False


def test_calendar_overdue_lesson_differs_from_planned_and_completed(
    client, calendar_owner, student_factory
):
    """2.5: просроченный урок отличается от запланированного и проведённого."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Статус")
    overdue_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="planned",
        starts_at=datetime(2020, 1, 8, 10, 0),
    )
    completed_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="completed",
        starts_at=datetime(2020, 1, 9, 10, 0),
    )
    planned_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="planned",
        starts_at=datetime(2099, 2, 3, 10, 0),
    )

    past = client.get("/tutor/calendar?start=2020-01-06")
    future = client.get("/tutor/calendar?start=2099-02-02")

    assert "cal-event--overdue" in _card(past.text, overdue_id)
    assert "cal-event--overdue" not in _card(past.text, completed_id)
    assert "cal-event--overdue" not in _card(future.text, planned_id)


def test_calendar_day_header_counts_real_lessons(client, calendar_owner, student_factory):
    """2.6: счётчик шапки дня и точки — по реальным урокам недели."""
    from app.common.colors import PALETTE

    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Счёт", color=PALETTE[9]
    )
    _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 12, 10, 0),
    )
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "1 урок" in response.text
    assert f"--dot: {PALETTE[9]}" in response.text


def test_calendar_empty_week_shows_explanation(client, calendar_owner):
    """2.6: пустая неделя — пояснение, сетка и шапка на месте."""
    response = client.get("/tutor/calendar?start=2026-11-09")
    assert response.status_code == 200
    assert "свободная неделя" in response.text
    assert "cal-dayhead" in response.text
    assert "cal-times" in response.text


# --------------------------------------------------------------------------
# 4.1 Режимы раскраски: серверное окрашивание по `?color=`
# --------------------------------------------------------------------------

def test_calendar_color_mode_target_uses_target_color(
    client, calendar_owner, student_factory
):
    """4.1: «По цели» — акцент карточки из `students.color` (и по умолчанию)."""
    from app.common.colors import PALETTE

    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Цвет", color=PALETTE[5]
    )
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 3, 10, 0),
    )

    default = client.get("/tutor/calendar?start=2099-02-02")
    explicit = client.get("/tutor/calendar?start=2099-02-02&color=target")
    # Неизвестное значение — не ошибка: режим по умолчанию.
    bogus = client.get("/tutor/calendar?start=2099-02-02&color=bogus")

    for response in (default, explicit, bogus):
        assert response.status_code == 200
        assert f"--accent: {PALETTE[5]}" in _card(response.text, lesson_id)


def test_calendar_color_mode_status_uses_status_colors(
    client, calendar_owner, student_factory
):
    """4.1: «По статусу» — синий/красный/серый вместо цвета цели."""
    from app.common.colors import PALETTE
    from app.calendar.services.color_mode import (
        STATUS_COMPLETED_COLOR,
        STATUS_OVERDUE_COLOR,
        STATUS_PLANNED_COLOR,
    )

    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Статусный", color=PALETTE[1]
    )
    overdue_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="planned",
        starts_at=datetime(2020, 1, 8, 10, 0),
    )
    completed_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="completed",
        starts_at=datetime(2020, 1, 9, 10, 0),
    )
    planned_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="planned",
        starts_at=datetime(2099, 2, 3, 10, 0),
    )

    past = client.get("/tutor/calendar?start=2020-01-06&color=status")
    future = client.get("/tutor/calendar?start=2099-02-02&color=status")

    assert f"--accent: {STATUS_OVERDUE_COLOR}" in _card(past.text, overdue_id)
    assert f"--accent: {STATUS_COMPLETED_COLOR}" in _card(past.text, completed_id)
    assert f"--accent: {STATUS_PLANNED_COLOR}" in _card(future.text, planned_id)
    # Цвет цели в этом режиме не используется.
    assert f"--accent: {PALETTE[1]}" not in past.text
    assert f"--accent: {PALETTE[1]}" not in future.text


def test_calendar_color_mode_group_uses_group_color(
    client, calendar_owner, group_factory
):
    """4.1: «По цели» для группового урока — цвет группы."""
    from app.common.colors import PALETTE

    group_id = group_factory(
        tutor_id=calendar_owner, name="Цветная группа", color=PALETTE[11]
    )
    lesson_id = _insert_lesson(
        calendar_owner, student_id=None, group_id=group_id,
        starts_at=datetime(2099, 2, 4, 10, 0),
    )
    response = client.get("/tutor/calendar?start=2099-02-02&color=target")
    assert f"--accent: {PALETTE[11]}" in _card(response.text, lesson_id)


def test_calendar_color_mode_control_markup(client):
    """4.2: вместо демо-кнопки — работающий контрол режима раскраски."""
    _login(client)
    page = client.get("/tutor/calendar?start=2026-10-12")
    text = page.text

    # Кнопка панели подписана активным режимом, меню — два режима.
    assert 'id="cal-color"' in text
    assert "Цвет: по ученику" in text
    assert 'data-color-set="target"' in text
    assert 'data-color-set="status"' in text
    assert ">По ученику</button>" in text
    assert ">По статусу</button>" in text
    # Перед названием «Цвет» — иконка палитры (Lucide, локальный вендор).
    assert re.search(
        r'id="cal-color".*?<i data-lucide="palette"[^>]*></i>\s*<span[^>]*>'
        r'Цвет: по ученику</span>',
        text,
        re.S,
    ), "Перед подписью «Цвет» нет иконки палитры"
    # Демо-заглушки больше нет.
    assert "Цвет: ученик" not in text
    assert "pickColor" not in _calendar_js()

    # Активный режим приходит с сервера и определяет подпись кнопки.
    status = client.get("/tutor/calendar?start=2026-10-12&color=status")
    assert "Цвет: по статусу" in status.text
    assert 'data-color-mode="status"' in status.text


def test_calendar_color_mode_persists_and_participates_in_requests():
    """4.2: выбор режима живёт в localStorage и уходит в hx-get недели.

    Браузерных тестов в проекте нет — поведение проверяется по исходнику
    компонента (тот же приём, что у остальных статических JS-проверок).
    """
    js = _calendar_js()

    # Ключ хранилища и обе операции над ним.
    assert "COLOR_STORAGE_KEY" in js
    assert "localStorage.getItem" in js
    assert "localStorage.setItem" in js

    # Смена режима: состояние → хранилище → перерисовка недели.
    setter = js[js.index("setColorMode: function"):js.index("applyColorMode: function")]
    assert "this.storeColorMode()" in setter
    assert "this.reloadWeek()" in setter

    # Режим участвует в адресах htmx: листание и подписка lesson-saved.
    assert "withColor: function" in js
    assert '"color=" + this.colorMode' in js
    assert "applyColorMode: function" in js
    assert 'querySelectorAll(\'[hx-get^="/tutor/calendar"]\')' in js

    # Восстановление выбора при открытии страницы.
    init = js[js.index("init: function"):js.index("readColorMode: function")]
    assert "this.readColorMode()" in init
    assert "this.reloadWeek()" in init


def test_calendar_menus_close_after_htmx_swap(client):
    """Меню «Цвет» и «⋮» скрываются и после подмены области календаря.

    Регрессия: htmx по умолчанию «устаканивает» атрибуты (`attributesToSettle`)
    и после свопа переносил class/style со старого элемента на новый с тем же
    id. Перенос затирал `style="display: none"`, выставленный Alpine, — меню
    оставались раскрытыми, а `x-show` продолжал менять только состояние.
    Общий фикс — пустой список в `app.js`; меню при этом управляются
    `x-show` + `x-cloak` и закрываются по клику вне и Escape.
    """
    _login(client)
    text = client.get("/tutor/calendar?start=2026-10-12").text

    # Оба меню скрыты декларативно, а не серверным style.
    for menu_id in ("cal-color-menu", "cal-more-menu"):
        menu = re.search(rf'<ul[^>]*id="{menu_id}"[^>]*>', text)
        assert menu, f"Меню #{menu_id} нет в разметке"
        assert "x-cloak" in menu.group(0), menu.group(0)
        assert 'x-show="' in menu.group(0), menu.group(0)

    # Фикс живёт в общем app.js: htmx не переносит атрибуты при свопе.
    app_js = (_STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "htmx.config.attributesToSettle = []" in app_js
    # Скрипт идёт после htmx — иначе `window.htmx` ещё не существует.
    assert text.index("/static/htmx.min.js") < text.index("/static/app.js")


# --------------------------------------------------------------------------
# 4.3 Точка шапки дня и карточка урока — один акцент
# --------------------------------------------------------------------------

def test_calendar_dot_and_card_share_accent(
    client, calendar_owner, student_factory
):
    """4.3: точка дня и карточка урока окрашены одним правилом в обоих режимах.

    Раскраску считает сервер (`event_accent`), поэтому точка шапки и
    карточка не могут разойтись (design.md D5).
    """
    from app.calendar.services.color_mode import STATUS_PLANNED_COLOR
    from app.common.colors import PALETTE

    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Точка", color=PALETTE[3]
    )
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 3, 10, 0),
    )

    for mode, expected in (("target", PALETTE[3]), ("status", STATUS_PLANNED_COLOR)):
        page = client.get(f"/tutor/calendar?start=2099-02-02&color={mode}").text
        # Урок один — в шапке ровно одна точка, её цвет равен акценту карточки.
        dots = re.findall(r'<i class="cal-dot" style="--dot: ([^"]+)"></i>', page)
        assert dots == [expected], (mode, dots)
        assert f"--accent: {expected}" in _card(page, lesson_id)


def test_calendar_status_dots_match_cards_in_one_day(
    client, calendar_owner, student_factory
):
    """4.3: разные статусы в одном дне — разные точки, совпадающие с карточками."""
    from app.calendar.services.color_mode import (
        STATUS_COMPLETED_COLOR,
        STATUS_OVERDUE_COLOR,
    )

    student_id = student_factory(tutor_id=calendar_owner, first_name="Статусы")
    overdue_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="planned",
        starts_at=datetime(2020, 1, 8, 10, 0),
    )
    completed_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="completed",
        starts_at=datetime(2020, 1, 8, 12, 0),
    )

    page = client.get("/tutor/calendar?start=2020-01-06&color=status").text
    dots = set(re.findall(r'<i class="cal-dot" style="--dot: ([^"]+)"></i>', page))
    assert dots == {STATUS_OVERDUE_COLOR, STATUS_COMPLETED_COLOR}
    assert f"--accent: {STATUS_OVERDUE_COLOR}" in _card(page, overdue_id)
    assert f"--accent: {STATUS_COMPLETED_COLOR}" in _card(page, completed_id)


# --------------------------------------------------------------------------
# 5.3–5.5 Перенос урока перетаскиванием: сервер, подавление клика, completed
# --------------------------------------------------------------------------

def test_calendar_drag_persists_move_to_server():
    """5.3: завершённый drag шлёт POST с датой и временем карточки.

    Браузерных тестов в проекте нет — поведение проверяется по исходнику
    компонента, как и остальные JS-проверки календаря.
    """
    js = _calendar_js()

    # Конец жеста вызывает сохранение, передавая карточку и новое начало.
    end = js[js.index("onDragEnd: function"):js.index("moveLesson: function")]
    assert "this.moveLesson(card, newMin)" in end

    # Запрос уходит только для реального урока и несёт дату/время.
    mover = js[js.index("moveLesson: function"):js.index("elementUnder: function")]
    assert 'window.htmx.ajax("POST", "/tutor/lessons/" + lessonId + "/move"' in mover
    assert 'date: card.getAttribute("data-date")' in mover
    assert "time: formatClock(startMin)" in mover
    # Ответ не подменяет DOM — неделю перерисует `lesson-saved`.
    assert 'swap: "none"' in mover
    # Без id урока (демо-слот) запроса нет.
    assert "if (!lessonId || !window.htmx) return;" in mover


def test_calendar_click_after_drag_is_suppressed(client, calendar_owner, student_factory):
    """5.4: клик, который браузер эмитит после drag, не открывает форму.

    Карточка несёт `hx-get` на редактирование (design.md D7), поэтому без
    подавителя перенос открывал бы модалку. Гасим в capture-фазе на
    постоянном корне — раньше слушателей htmx на самой карточке.
    """
    student_id = student_factory(tutor_id=calendar_owner, first_name="Тащат")
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 14, 14, 0),
    )
    page = client.get("/tutor/calendar?start=2026-10-12")
    # Конфликт возможен только потому, что карточка кликабельна.
    assert f'hx-get="/tutor/lessons/{lesson_id}/edit"' in _card(page.text, lesson_id)

    js = _calendar_js()
    assert "_suppressClick" in js
    # Флаг ставится при переносе и снимается следующим жестом.
    mover = js[js.index("moveLesson: function"):js.index("elementUnder: function")]
    assert "this._suppressClick = true;" in mover
    down = js[js.index("onEventPointerDown: function"):js.index("onDragMove: function")]
    assert "this._suppressClick = false;" in down
    # Гашение — в capture-фазе, до htmx.
    assert "onSuppressedClick" in js
    assert "event.stopImmediatePropagation()" in js
    init = js[js.index("init: function"):js.index("readColorMode: function")]
    assert "self.onSuppressedClick(event);" in init
    assert "}, true);" in init


def test_calendar_completed_lesson_is_not_draggable(
    client, calendar_owner, student_factory
):
    """5.5: проведённый урок не участвует в жесте — время не меняется."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Проведён")
    completed_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="completed",
        starts_at=datetime(2026, 10, 14, 14, 0),
    )
    planned_id = _insert_lesson(
        calendar_owner, student_id=student_id, status="planned",
        starts_at=datetime(2026, 10, 15, 14, 0),
    )
    page = client.get("/tutor/calendar?start=2026-10-12").text

    # Разметка различает уроки: только проведённый помечен data-completed.
    assert 'data-completed="true"' in _card(page, completed_id)
    assert 'data-completed="true"' not in _card(page, planned_id)

    # Жест не начинается для помеченной карточки.
    js = _calendar_js()
    down = js[js.index("onEventPointerDown: function"):js.index("onDragMove: function")]
    assert 'card.hasAttribute("data-completed")' in down


def test_calendar_card_tooltip_follows_drag():
    """Подсказка карточки пересобирается после переноса урока.

    `title` содержит интервал времени, поэтому после drag старое значение
    показывало бы прежнее время. Пересборка идёт общим методом
    `setCardTitle`, чтобы рендер и перенос не расходились.
    """
    js = _calendar_js()

    assert "setCardTitle: function" in js
    render = js[js.index("renderCard: function"):js.index("setCardTitle: function")]
    assert "this.setCardTitle(card, data.startMin, data.duration)" in render

    end = js[js.index("onDragEnd: function"):js.index("moveLesson: function")]
    assert "this.setCardTitle(card, newMin, drag.duration)" in end


# --------------------------------------------------------------------------
# Замена демо-тестов уроков тестами реальных данных (задача 6.1)
# Демо-слоты и демо-отпуск остаются: их спеки в change не входят.
# --------------------------------------------------------------------------

def test_calendar_real_lessons_fill_weekdays_only(
    client, calendar_owner, student_factory
):
    """Уроки БД раскладываются по будням; выходные остаются пустыми.

    Заменяет демо-тест «будни расписаны, выходные свободны»: расписание
    теперь приходит из БД, а не из генератора.
    """
    student_id = student_factory(tutor_id=calendar_owner, first_name="Будни")
    weekday_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 3, 10, 0),  # вторник
    )
    # Урок в субботу той же недели — он тоже должен попасть в сетку.
    saturday_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 7, 10, 0),
    )
    page = client.get("/tutor/calendar?start=2099-02-02").text

    assert _card(page, weekday_id), "Урока буднего дня нет в сетке"
    assert _card(page, saturday_id), "Урока субботы нет в сетке"
    # Выходные по-прежнему помечены штриховкой и плашкой «Выходной».
    assert page.count("cal-day--weekend") == 2
    assert page.count(">Выходной<") == 2


def test_calendar_real_lesson_card_fields(
    client, calendar_owner, student_factory, group_factory
):
    """Карточка реального урока: цель с ценой, интервал, пометка группы.

    Заменяет демо-тест «урок несёт ученика, цену, длительность и цвет»:
    те же поля, но источник — строки БД.
    """
    from app.common.colors import PALETTE

    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Иван", last_name="Иванов",
        color=PALETTE[2],
    )
    individual_id = _insert_lesson(
        calendar_owner, student_id=student_id, price=1200,
        starts_at=datetime(2099, 2, 3, 10, 0), duration_min=40,
    )
    group_id = group_factory(tutor_id=calendar_owner, name="Группа 8Б")
    group_lesson_id = _insert_lesson(
        calendar_owner, student_id=None, group_id=group_id, type="group",
        starts_at=datetime(2099, 2, 4, 16, 0), duration_min=60,
    )
    page = client.get("/tutor/calendar?start=2099-02-02").text

    individual = _card(page, individual_id)
    assert "Иван И." in individual
    assert "1\u00a0200\u00a0₽" in individual
    assert "10:00 – 10:40" in individual
    assert f"--accent: {PALETTE[2]}" in individual
    assert "Группа</span>" not in individual

    group_lesson = _card(page, group_lesson_id)
    assert "Группа 8Б" in group_lesson
    assert ">Группа</span>" in group_lesson
    assert "16:00 – 17:00" in group_lesson


def test_calendar_card_shows_target_name_as_own_line(
    client, calendar_owner, student_factory
):
    """Имя цели — отдельная строка карточки, цена и время — во второй.

    Короткий урок (30–40 минут) занимает 24–32 px: две строки по 14 px
    помещаются только при плотной вёрстке. Раньше заголовок был одной
    строкой «Имя · цена», сжимался до нуля и карточка показывала только
    время — имени ученика не было видно вовсе.
    """
    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Иван", last_name="Иванов"
    )
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id, price=1200,
        starts_at=datetime(2099, 2, 3, 10, 0), duration_min=40,
    )
    card = _card(client.get("/tutor/calendar?start=2099-02-02").text, lesson_id)

    # Имя — в собственной строке, без цены внутри неё.
    title = re.search(r'cal-event__title">(.*?)</span>', card, re.S)
    assert title, "В карточке нет строки с именем цели"
    assert title.group(1).strip() == "Иван И."
    assert "₽" not in title.group(1)

    # Цена и время — во второй строке, отдельными элементами.
    assert 'class="cal-event__meta"' in card
    assert 'class="cal-event__price">1\u00a0200\u00a0₽<' in card
    assert 'class="cal-event__time">10:00 – 10:40<' in card


def test_calendar_card_without_price_has_no_zero_rubles(
    client, calendar_owner, student_factory
):
    """Урок без цены: блок цены отсутствует, а не показывает «0 ₽».

    «0 ₽» ничего не сообщает и занимает место в короткой карточке; имя
    цели при этом остаётся на месте.
    """
    student_id = student_factory(tutor_id=calendar_owner, first_name="Пётр")
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 3, 10, 0), duration_min=40,
    )
    card = _card(client.get("/tutor/calendar?start=2099-02-02").text, lesson_id)

    assert "cal-event__title\">Пётр</span>" in card
    assert "cal-event__price" not in card
    assert "0\u00a0₽" not in card
    assert "10:00 – 10:40" in card


def test_calendar_card_has_full_text_tooltip(client, calendar_owner, student_factory):
    """Полный текст карточки доступен во всплывающей подсказке `title`.

    В коротком уроке вторая строка скрыта (см. @container в styles.css),
    поэтому цена и интервал должны читаться хотя бы в подсказке.
    """
    student_id = student_factory(
        tutor_id=calendar_owner, first_name="Иван", last_name="Иванов"
    )
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id, price=1200,
        starts_at=datetime(2099, 2, 3, 10, 0), duration_min=40,
    )
    card = _card(client.get("/tutor/calendar?start=2099-02-02").text, lesson_id)

    assert 'title="Иван И. · 1\u00a0200\u00a0₽ · 10:00 – 10:40"' in card


def test_calendar_card_name_is_not_clipped_by_flex():
    """Вёрстка карточки не даёт имени исчезнуть в коротком уроке.

    Регрессия: `.cal-event` — flex-колонка с `overflow: hidden`, строки
    сжимались, и заголовок с именем получал высоту 3 px. Строки карточки
    объявлены `flex: 0 0 auto`, а вторая строка скрывается контейнерным
    запросом, когда высоты не хватает.
    """
    css = _styles_css()

    title = re.search(r"\.cal-event__title\s*\{([^}]*)\}", css)
    assert title, "В styles.css нет правила .cal-event__title"
    assert "flex: 0 0 auto" in title.group(1), "Строка имени не должна сжиматься"

    meta = re.search(r"\.cal-event__meta\s*\{([^}]*)\}", css)
    assert meta, "В styles.css нет правила .cal-event__meta"
    assert "flex: 0 0 auto" in meta.group(1)

    # Контейнерный запрос по высоте карточки скрывает вторую строку.
    container = re.search(
        r"@container \(max-height: \d+px\)\s*\{\s*\.cal-event__meta[^{]*\{[^}]*display:\s*none",
        css,
    )
    assert container, "Нет @container-правила, скрывающего вторую строку"
    card = re.search(r"\.cal-event\s*\{([^}]*)\}", css)
    assert card and "container-type: size" in card.group(1), (
        "Карточка должна быть контейнером запросов по размеру"
    )
