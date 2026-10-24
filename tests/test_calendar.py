"""Тесты календаря: unit-тесты сервисов недели и страницы GET /tutor/calendar.

Демо-генератор удалён (change add-tutor-unavailability): календарь наполняется
реальными уроками из БД и отметками недоступности.
"""

import re
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.calendar.services.presentation import lessons_word
from app.calendar.services.week import week_start
from app.common.services.tutor_time import system_zone_name

PASSWORD = "Секретный-Пароль-1"
ROOT = Path(__file__).resolve().parent.parent


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
def calendar_owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id.

    Зона задана явно (UTC), иначе тесты зависели бы от системной зоны
    машины: `calendar_owner` регистрируется через форму, а пустое поле
    карточки даёт fallback на зону сервера (спека tutor-timezone).
    Наивные `starts_at` в БД тогда показываются в сетке как есть.
    """
    tutor_id = tutor_factory(
        email="calendar-owner@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "calendar-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


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


def _tutor(timezone: str = "UTC") -> SimpleNamespace:
    """Карточка репетитора для сервисов календаря: нужна только её зона.

    Простой объект вместо ORM-строки — значение переживает закрытие
    сессии. По умолчанию UTC: тесты не зависят от системной зоны машины
    (спека tutor-timezone).
    """
    return SimpleNamespace(timezone=timezone)


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
    """Полная страница (без HX-Request): каркас с сайдбаром и панель управления.

    Область подмены `#calendar-swap` живёт только в полной странице —
    htmx-фрагмент её не заворачивает (см. test_calendar_htmx_fragment_only).
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert response.status_code == 200
    for label in ("Сегодня", "Добавить", "Ссылка на окна", "Цвет: по ученику"):
        assert label in response.text
    assert 'id="calendar-swap"' in response.text
    assert 'class="sidebar"' in response.text


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


@pytest.mark.parametrize(
    ("timezone", "expected"),
    [
        (None, None),  # пустое поле → системная зона сервера
        ("Europe/Samara", "Europe/Samara"),
    ],
    ids=["system-zone-fallback", "explicit-zone"],
)
def test_calendar_timezone_badge(client, tutor_factory, timezone, expected):
    """Бейдж `.cal-tz` подписывает зону сетки: заданную или системную.

    Бейдж показывается всегда (design D2): при пустом поле карточки это
    системная зона сервера, а не пустое место — иначе непонятно, в какой
    зоне показано время сетки.
    """
    tutor_factory(email="tz-badge@example.com", password=PASSWORD, timezone=timezone)
    client.post(
        "/tutor/login",
        data={"email": "tz-badge@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    response = client.get("/tutor/calendar?start=2026-10-12")

    assert 'class="cal-tz"' in response.text
    assert (expected or system_zone_name() or "UTC") in response.text


# --------------------------------------------------------------------------
# 3.3 Карточки занятий и состояние сетки (реальные уроки из БД)
# --------------------------------------------------------------------------

def test_calendar_week_without_marks_has_no_weekend_automation(
    client, calendar_owner, student_factory
):
    """Неделя без отметок: ни выходных, ни штриховки по номеру дня недели.

    Единственный источник выходных — отметки в таблице `tutor_unavailability`
    (спека calendar, «Выходные задаёт репетитор отметками»): автоматическая
    плашка и штриховка сб/вс удалены, штриховка осталась только у отмеченных
    дней (`.cal-day--unavailable`).
    """
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
    text = response.text

    assert "Выходной" not in text
    assert "cal-day--weekend" not in text
    assert "cal-dayhead--weekend" not in text
    assert "cal-day--unavailable" not in text
    assert "cal-dayhead__off--unavailable" not in text
    assert "2 урока" in text  # понедельник: два урока репетитора


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


# --------------------------------------------------------------------------
# 5.1 Клиентский слой: calendar.js и данные четвертей часа
# --------------------------------------------------------------------------

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
    """3.2: calendar.js/lessons.js до alpine.min.js, `#modal` вне области свопа.

    Компонент подписывается на `alpine:init`, а defer-скрипты выполняются
    в порядке документа — позже Alpine регистрация не успевает сработать.
    Форма урока живёт в контейнере `#modal`, который htmx не подменяет
    при листании недель (design.md D6): иначе открытая модалка исчезала
    бы вместе с областью `#calendar-swap`.
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert '<script src="/static/calendar.js" defer></script>' in response.text
    assert '<script src="/static/lessons.js" defer></script>' in response.text
    assert (
        response.text.index("/static/calendar.js")
        < response.text.index("/static/lessons.js")
        < response.text.index("/static/alpine.min.js")
    )
    # Точка монтирования: Alpine-компонент на корне области подмены.
    assert 'x-data="calendarGrid"' in response.text
    # Контейнер модалки есть и находится вне области подмены.
    swap = re.search(
        r'<div id="calendar-swap".*?</section>', response.text, re.S
    )
    assert swap, "Область #calendar-swap не найдена"
    assert 'id="modal"' not in swap.group(0)
    assert '<div id="modal"></div>' in response.text

def test_calendar_lesson_card_opens_edit_form(client, calendar_owner, student_factory):
    """3.3: карточка урока несёт edit-ссылку в #modal."""
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

    # Август: демо-отпуска больше нет — заглушки .cal-vacation в сетке нет
    # вовсе, а без уроков страница остаётся пустой неделей.
    august = client.get("/tutor/calendar?start=2026-08-03")
    assert 'class="cal-vacation"' not in august.text
    assert "/edit" not in august.text


def test_calendar_entry_points_open_lesson_form(client):
    """3.4: клик по четверти, «Добавить» и FAB открывают форму создания урока.

    Все точки входа ведут на `GET /tutor/lessons/new` с префиллом
    `starts_at` (design.md D9): четверть — своя дата/время, кнопка —
    ближайшая будущая четверть (`prefillMoment`).
    """
    _login(client)
    page = client.get("/tutor/calendar?start=2026-10-12")
    # Адрес формы — в разметке корня (JS читает data-lesson-new).
    assert 'data-lesson-new="/tutor/lessons/new"' in page.text
    # Все три обработчика на месте.
    assert '@click="openSlot($event.currentTarget)"' in page.text
    assert 'id="cal-add" @click="openForm()"' in page.text
    assert 'class="cal-fab" type="button" @click="openForm()"' in page.text

    js = _calendar_js()
    # Клик по четверти: своя дата/время четверти в форме создания; третий
    # аргумент — признак подтверждения для отмеченного дня (design.md D5).
    slot_open = js[js.index("openSlot: function"):js.index("openLessonForm: function")]
    assert "this.openLessonForm(data.date, data.time" in slot_open
    # Кнопка «Добавить»: ближайшая будущая четверть из prefillMoment.
    form_open = js[js.index("openForm: function"):js.index("toggleMore: function")]
    assert "prefillMoment()" in form_open
    assert "openLessonForm(moment.date, moment.time)" in form_open
    # Сама форма запрашивается htmx-ом в #modal с параметром префилла.
    helper = js[js.index("openLessonForm: function"):js.index("prefillMoment: function")]
    assert 'window.htmx.ajax("GET", url + query' in helper
    assert '"?starts_at="' in helper
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
    # Подписки: урок, недоступность и окно для записи перерисовывают неделю
    # с сервера (спека calendar, «Сохранение окна обновляет неделю»).
    assert (
        'hx-trigger="lesson-saved from:body, unavailability-saved from:body, '
        'slot-saved from:body"' in tag
    )
    assert 'hx-target="#calendar-swap"' in tag

    js = _calendar_js()
    assert "syncWeekParam" in js
    # Адрес перерисовки собирается из видимой недели и активного режима.
    assert "this.withColor(this.weekPath())" in js
    # Подписка на подмену области — у постоянного корня.
    assert 'root.addEventListener("htmx:afterSwap"' in js


def test_calendar_demo_layer_is_removed(client):
    """8.1/8.2: демо-слой календаря удалён целиком.

    Урок, отпуск, окно и запись живут в БД: календарь больше не держит
    клиентских модалок «Новый слот» и «Запись на слот», не рендерит
    карточки из `<template>` и не создаёт ничего только в DOM. Окно
    открывается серверным диалогом, запись приходит с публичной страницы.
    """
    _login(client)
    text = client.get("/tutor/calendar?start=2026-10-12").text
    # Демо-выбора ученика и «Сохранить» в календаре больше нет.
    assert 'id="cal-student"' not in text
    assert "cal-student-field" not in text
    assert "saveLesson" not in text
    assert "demo_students" not in text
    # Клиентских модалок окна и записи нет — только серверный диалог.
    assert 'id="cal-slot-date"' not in text
    assert 'id="cal-booking-form"' not in text
    assert 'id="cal-event-template"' not in text
    assert 'id="cal-vacation-form"' not in text

    js = _calendar_js()
    for gone in (
        "saveLesson",
        "createVacation",
        "openSlotDialog",
        "createSlot",
        "openBooking",
        "closeBooking",
        "confirmBooking",
        "renderCard",
        "layoutDay",
        "cal-event--booked",
    ):
        assert gone not in js, gone
    # Ни одного сетевого вызова в компоненте нет вообще.
    assert "fetch(" not in js
    assert "XMLHttpRequest" not in js


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
    """«Ссылка на окна» и «Цвет»: селекторы на месте, битых ссылок нет."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    main = re.search(r"<main class=\"main\">(.*?)</main>", response.text, re.S)
    assert main, "На странице нет <main>"
    area = main.group(1)

    # Селекторы кнопок и их обработчики.
    assert 'id="cal-link"' in area
    assert '@click="copyWeekLink()"' in area
    assert 'id="cal-color"' in area
    assert "colorOpen" in area              # выпадающий список кнопки цвета
    # Поле показа ссылки, когда буфер обмена недоступен (задача 7.5).
    assert 'class="cal-link-fallback"' in area
    assert 'id="cal-link-url"' in area
    assert 'class="cal-toast"' in area      # подтверждение копирования

    # У самих кнопок нет href/action — они не ведут на маршруты.
    for button in re.findall(r'<button[^>]*id="cal-(?:link|color)"[^>]*>', area):
        assert "href=" not in button, button
        assert "action=" not in button, button

    # Копирование идёт через clipboard, а ссылка строится из текущей сетки,
    # а не из устаревших data-*.
    js = (Path(__file__).resolve().parent.parent / "app" / "static" / "calendar.js").read_text(
        encoding="utf-8"
    )
    assert "clipboard.writeText" in js
    assert ".cal-day[data-date]" in js
    # Тост «демо» удалён: копирование реальное (задача 7.5).
    assert "Демо: ссылка на неделю скопирована" not in js



def test_week_start_normalizes_to_monday():
    """`?start=` любой день недели → понедельник; строка ISO тоже работает."""
    assert week_start(date(2026, 10, 12)) == date(2026, 10, 12)  # уже понедельник
    assert week_start(date(2026, 10, 15)) == date(2026, 10, 12)  # четверг
    assert week_start(date(2026, 10, 18)) == date(2026, 10, 12)  # воскресенье
    assert week_start("2026-10-14") == date(2026, 10, 12)  # строка ?start=


def test_week_start_rejects_broken_string():
    """Кривая строка — ValueError: вьюха сама подставляет текущую неделю."""
    with pytest.raises(ValueError):
        week_start("2026-13-45")


def test_lessons_word_declension():
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
    """Задача 7.3: «Добавить слот» открывает серверный диалог окна.

    Диалог живёт в `slot/_dialog.html` и приходит в `#modal` по hx-get —
    календарь больше не держит своей копии формы окна. Поля диалога
    проверяются на его собственном ответе.
    """
    _login(client)
    page = client.get("/tutor/calendar?start=2026-10-12").text

    assert "Добавить слот" in page
    entry = re.search(r'<button[^>]*id="cal-add-slot"[^>]*>', page)
    assert entry, "Пункта меню «Добавить слот» нет в разметке"
    assert 'hx-get="/tutor/slots/new"' in entry.group(0)
    assert 'hx-target="#modal"' in entry.group(0)
    assert 'hx-swap="innerHTML"' in entry.group(0)

    # Сам диалог: одно окно по умолчанию, поля даты и времени на месте.
    dialog = client.get("/tutor/slots/new").text
    assert "Новые окна для записи" in dialog
    date_input = re.search(r'id="slot-new-date"[^>]*', dialog)
    assert date_input, "Поля даты окна нет в диалоге"
    assert 'type="date"' in date_input.group(0)
    time_input = re.search(r'id="slot-new-time"[^>]*', dialog)
    assert time_input, "Поля времени окна нет в диалоге"
    assert 'type="time"' in time_input.group(0)
    # Поля выбора ученика в диалоге нет — урок создаётся формой Уроков.
    assert "cal-student-field" not in dialog
    assert 'id="cal-student"' not in dialog


def test_calendar_slot_styles_static():
    """7.6: стили окна — состояние задаёт класс, темы — только токен.

    Каждое состояние окна (`free`, `pending`, `booking`, `lesson`, `past`)
    описано своим правилом, приглушение занятых и прошедших — отдельным
    классом. Светлая и тёмная темы заданы переменной `--cal-slot-accent`
    (токены в `:root` и `.dark`), поэтому компонентные правила тему не
    дублируют.
    """
    css = _styles_css()

    assert ".cal-event--slot" in css
    # Все пять состояний из спеки описаны правилами.
    for state in ("free", "pending", "booking", "lesson", "past"):
        assert f".cal-event--slot-{state}" in css, state
    assert ".cal-event--muted" in css

    slot_block = re.search(r"\.cal-event--slot\s*\{(.*?)\}", css, re.S)
    assert slot_block, "Блока .cal-event--slot нет в styles.css"
    assert "border-style: dashed" in slot_block.group(1)
    assert "--cal-slot-accent" in slot_block.group(1)

    # Собственный цвет окна — на переменных обеих тем.
    assert "--cal-slot-accent" in css
    root_block = re.search(r":root\s*\{(.*?)\n  \}", css, re.S)
    dark_block = re.search(r"\.dark\s*\{(.*?)\n  \}", css, re.S)
    assert root_block and "--cal-slot-accent" in root_block.group(1)
    assert dark_block and "--cal-slot-accent" in dark_block.group(1)


def test_calendar_slot_state_is_not_clipped():
    """7.6: подпись состояния окна не сжимается в короткой карточке.

    Регрессия: `.cal-event` — flex-колонка, и подпись состояния
    схлопывалась до нулевой высоты — на окне оставалось одно время.
    Подпись (`.cal-event__title` в ветке окна) объявлена `flex: 0 0 auto`,
    а интервал времени скрывается контейнерным запросом, когда строк не
    помещается.
    """
    css = _styles_css()

    state = re.search(
        r"\.cal-event--slot \.cal-event__title\s*\{([^}]*)\}", css
    )
    assert state, "В styles.css нет правила .cal-event--slot .cal-event__title"
    assert "flex: 0 0 auto" in state.group(1), "Подпись состояния не должна сжиматься"

    slot_container = re.search(
        r"@container \(max-height: \d+px\)\s*\{\s*"
        r"\.cal-event--slot \.cal-event__meta\s*\{[^}]*display:\s*none",
        css,
    )
    assert slot_container, (
        "Нет @container-правила, скрывающего время окна в короткой карточке"
    )


def test_calendar_slot_excluded_from_drag_static():
    """Задача 2.3: в ветке начала драга есть исключение .cal-event--slot.

    Окно — не урок: жест по его карточке не начинается, поэтому клик по
    карточке всегда открывает диалог окна (спека calendar).
    """
    js = _calendar_js()
    start = js.index("onEventPointerDown")
    end = js.index("onDragMove")
    assert ".cal-event--slot" in js[start:end]


# --------------------------------------------------------------------------
# 7. Недоступность в календаре (спека calendar, change add-tutor-unavailability):
#    пункт меню «Отпуск и выходные», отмеченный день в сетке, guard клика —
#    SSR-разметка и статические проверки (design.md D6: без запуска JS)
# --------------------------------------------------------------------------

def test_calendar_more_menu_markup(client):
    """Задача 4.5: #cal-more сразу после #cal-add, пункты внутри меню.

    Прямая кнопка слота из панели переехала в меню: id и обработчик
    сохранены, поэтому существующий test_calendar_slot_dialog_markup
    проходит без правок. Пункт «Отпуск и выходные» открывает панель
    недоступности в #modal (design.md D8).
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
    # Пункт окна ведёт на серверный диалог окна, а не в клиентскую модалку.
    entry = re.search(r'<button[^>]*id="cal-add-slot"[^>]*>', items)
    assert entry, "Пункта «Добавить слот» нет в меню"
    assert 'hx-get="/tutor/slots/new"' in entry.group(0)
    assert '@click="closeMore()"' in entry.group(0)
    assert '@click.outside="closeMore()"' in items
    assert '@keydown.escape.window="closeMore()"' in items

    # Прямая кнопка слота из панели удалена: id встречается ровно один
    # раз — в меню. Клиентской модалки окна в календаре больше нет:
    # диалог окна — серверный (`slot/_dialog.html`).
    assert text.count('id="cal-add-slot"') == 1
    assert "openSlotDialog()" not in text


def test_calendar_more_menu_opens_unavailability_panel(client):
    """Пункт «Отпуск и выходные» открывает панель, а не форму урока.

    Кнопка несёт `hx-get` панели с целью `#modal` — форму урока она не
    открывает (спека calendar, «Пункт „Отпуск и выходные“ открывает
    панель недоступности»).
    """
    _login(client)
    text = client.get("/tutor/calendar?start=2026-10-12").text

    menu = re.search(r'<ul[^>]*id="cal-more-menu"[^>]*>.*?</ul>', text, re.S)
    assert menu, "Выпадающего меню #cal-more-menu нет в разметке"
    item = re.search(
        r'<button[^>]*id="cal-unavailability"[^>]*>.*?</button>', menu.group(0), re.S
    )
    assert item, "Пункта «Отпуск и выходные» нет в меню"
    button = item.group(0)
    assert "Отпуск и выходные" in button
    assert 'hx-get="/tutor/unavailability"' in button
    assert 'hx-target="#modal"' in button
    assert 'hx-swap="innerHTML"' in button
    # Меню закрывается выбором пункта.
    assert "closeMore()" in button
    # Старого пункта нет.
    assert "Добавить отпуск" not in text
    assert 'id="cal-add-vacation"' not in text


def test_calendar_more_menu_js_static():
    """Задача 4.5: moreOpen/toggleMore/closeMore, выбор пункта закрывает меню."""
    js = _calendar_js()
    assert "moreOpen" in js
    assert "toggleMore" in js
    assert "closeMore" in js
    # Пункт окна закрывает меню и открывает серверный диалог (hx-get в
    # разметке), поэтому клиентского состояния диалога больше нет.
    assert "openSlotDialog" not in js
    assert "closeModal" not in js


def test_calendar_unavailable_day_markup(
    client, calendar_owner, unavailability_factory
):
    """Задача 4.3: день с отметкой заштрихован, причина — в шапке.

    `.cal-vacation` из сетки удалён: отмеченный день — класс на колонке,
    `data-unavailable` с причиной и подпись в шапке вместо «Выходного».
    """
    unavailability_factory(
        tutor_id=calendar_owner,
        start_date=date(2026, 10, 14),
        end_date=date(2026, 10, 15),
    )
    text = client.get("/tutor/calendar?start=2026-10-12").text

    day = re.search(r'<div class="cal-day[^"]*"[^>]*data-date="2026-10-14"[^>]*>', text)
    assert day, "Колонки отмеченного дня нет в сетке"
    tag = day.group(0)
    assert "cal-day--unavailable" in tag
    assert 'data-unavailable="Отпуск"' in tag
    # Причина в шапке дня.
    assert "cal-dayhead__off--unavailable" in text
    assert "Отпуск" in text
    # Заглушка отпуска удалена.
    assert 'class="cal-vacation"' not in text

    # День без отметки — без класса и атрибута.
    free = re.search(r'<div class="cal-day[^"]*"[^>]*data-date="2026-10-12"[^>]*>', text)
    assert free and "cal-day--unavailable" not in free.group(0)
    assert "data-unavailable" not in free.group(0)


def test_calendar_unavailable_weekday_mark_labels_saturday(
    client, calendar_owner, unavailability_factory
):
    """Постоянный выходной в субботу: причина в шапке, воскресенье пустое.

    Плашки «Выходной» по календарю больше нет — подпись даёт только отметка
    (спека calendar, «Выходные задаёт репетитор отметками»).
    """
    unavailability_factory(
        tutor_id=calendar_owner, mode="weekday", weekday=5, until_date=date(2026, 12, 31)
    )
    text = client.get("/tutor/calendar?start=2026-10-12").text

    saturday = _dayhead(text, "сб")
    assert saturday, "Шапки субботы нет"
    assert "cal-dayhead__off--unavailable" in saturday
    assert 'title="Выходной">Выходной</span>' in saturday

    # Воскресенье без отметки: ни причины, ни плашки выходного.
    sunday = _dayhead(text, "вс")
    assert sunday, "Шапки воскресенья нет"
    assert "cal-dayhead__off" not in sunday
    assert "Выходной" not in sunday


def test_calendar_unavailable_day_keeps_lessons(
    client, calendar_owner, student_factory, unavailability_factory
):
    """Отметка не скрывает уроки дня: карточки остаются кликабельными."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Иван")
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 14, 14, 0),
    )
    unavailability_factory(
        tutor_id=calendar_owner,
        start_date=date(2026, 10, 14),
        end_date=date(2026, 10, 14),
    )
    text = client.get("/tutor/calendar?start=2026-10-12").text

    assert "cal-day--unavailable" in text
    card = _card(text, lesson_id)
    assert card, "Карточка урока пропала из отмеченного дня"
    assert f'hx-get="/tutor/lessons/{lesson_id}/edit"' in card


def test_calendar_empty_week_with_mark_is_not_free(
    client, calendar_owner, unavailability_factory
):
    """Неделя без уроков, но с отметкой: пояснения о «свободной неделе» нет."""
    unavailability_factory(
        tutor_id=calendar_owner,
        start_date=date(2026, 11, 9),
        end_date=date(2026, 11, 13),
    )
    text = client.get("/tutor/calendar?start=2026-11-09").text

    assert "свободная неделя" not in text
    assert "cal-day--unavailable" in text
    assert not re.search(r'class="cal-event[\s"]', text)


def test_calendar_period_reason_wins_over_weekday_on_render(
    client, calendar_owner, unavailability_factory
):
    """Приоритет D4 на уровне разметки: причина периода важнее «Выходного».

    Суббота 17.10 попадает и в период «Больничный», и в постоянный
    выходной — в шапке должна быть причина периода, а выходной доступен
    только во всплывающей подсказке.
    """
    unavailability_factory(
        tutor_id=calendar_owner,
        reason="sick",
        start_date=date(2026, 10, 16),
        end_date=date(2026, 10, 18),
    )
    unavailability_factory(tutor_id=calendar_owner, mode="weekday", weekday=5)

    text = client.get("/tutor/calendar?start=2026-10-12").text
    saturday = _dayhead(text, "сб")
    assert saturday, "Шапки субботы нет"
    # В шапке — «Больничный», а не «Выходной».
    assert ">Больничный</span>" in saturday
    # Обе причины — в подсказке.
    assert 'title="Больничный, Выходной"' in saturday


def test_calendar_confirm_guard_for_unavailable_day_static():
    """Задача 5.6: клик и drag спрашивают подтверждение для отмеченного дня.

    Раньше клик по дню с отпуском блокировался (`.cal-vacation`); теперь
    форма открывается после подтверждения, а признак подтверждения уходит
    в адрес формы и в тело переноса (design.md D5). При отказе карточка
    остаётся на месте: `confirm()` стоит до правки `data-date` и до
    `appendChild`.
    """
    js = _calendar_js()

    # Клик по четверти: причина читается с колонки, спрашивается confirm().
    slot = js[js.index("openSlot: function"):js.index("prefillMoment: function")]
    assert "unavailableReason(day)" in slot
    assert "window.confirm(" in slot
    # Подтверждение передаётся признаком, и только когда причина есть.
    assert 'reason ? "1" : ""' in slot
    assert '".cal-vacation"' not in slot
    # Признак подтверждения уходит в адрес формы (design.md D5, п. 4).
    helper = js[js.index("openLessonForm: function"):js.index("prefillMoment: function")]
    assert '"&ack_unavailable="' in helper

    # Перенос: подтверждение до любых правок карточки.
    end = js[js.index("onDragEnd: function"):js.index("moveLesson: function")]
    confirm_at = end.index("window.confirm(")
    append_at = end.index("day.appendChild(card)")
    date_at = end.index('card.setAttribute("data-date"')
    assert confirm_at < append_at, "confirm() должен идти до appendChild"
    assert confirm_at < date_at, "confirm() должен идти до смены data-date"
    assert "this.unavailableQuestion(reason)" in end

    # Перенос передаёт признак подтверждения.
    mover = js[js.index("moveLesson: function"):js.index("elementUnder: function")]
    assert "ack_unavailable" in mover


def test_calendar_has_no_vacation_leftovers():
    """Задача 6.3: в calendar.js и _area.html не осталось «отпускных» следов.

    Проверяется именно слово `vacation` (и его camelCase-формы): прежняя
    версия дополнительно перебирала токены вроде `vacationForm`, но они
    не могут встретиться без самого слова — цикл был недостижим.
    """
    js = _calendar_js()
    area = (
        ROOT / "app" / "calendar" / "templates" / "calendar" / "_area.html"
    ).read_text(encoding="utf-8")

    assert "vacation" not in js.lower()
    assert "vacation" not in area.lower()


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


def _dayhead(response_text: str, weekday_short: str) -> str:
    """Разметка шапки дня по короткому названию дня недели («сб», «вс»).

    Шапки идут подряд, поэтому блок ограничен началом следующей шапки или
    колонкой времени — иначе `.*?</div>` зацепил бы чужой день.
    """
    for match in re.finditer(
        r'<div class="cal-dayhead[^"]*">.*?(?=<div class="cal-dayhead|<div class="cal-times")',
        response_text,
        re.S,
    ):
        block = match.group(0)
        name = re.search(r'class="cal-dayhead__name">([^<]*)<', block)
        if name and name.group(1).strip() == weekday_short:
            return block
    return ""


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
        rows = week_lessons(db, calendar_owner, date(2026, 10, 12), _tutor())

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
        first = week_lessons(db, calendar_owner, date(2026, 10, 12), _tutor())
        second = week_lessons(db, calendar_owner, date(2026, 10, 19), _tutor())

    assert [row.lesson.id for row in first] == [sunday]
    assert [row.lesson.id for row in second] == [monday]


def test_week_bounds_are_local_midnights_in_utc():
    """Спека (задача 7.1): границы недели считаются по настенному времени.

    При зоне UTC+04 неделя с понедельника 12.10 открывается окном
    `11.10 20:00 UTC … 18.10 20:00 UTC`, а не `12.10 00:00 … 19.10 00:00`:
    границы переводятся по отдельности (design D3).
    """
    from app.calendar.services.week import week_bounds

    start, end = week_bounds(date(2026, 10, 12), _tutor("Europe/Ulyanovsk"))

    assert start == datetime(2026, 10, 11, 20, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 18, 20, 0, tzinfo=UTC)


def test_week_lessons_keeps_late_evening_lesson_on_its_own_day(
    calendar_owner, student_factory
):
    """Спека (задача 7.1): урок 23:30 местного остаётся в понедельнике.

    Хранится он как 20:30 UTC предыдущих суток — по UTC-дате это была бы
    воскресенье, но окно недели считается по локальным полуночам, поэтому
    урок попадает в свою неделю и на свой день.
    """
    from app.calendar.services.week import week_lessons
    from app.database import SessionLocal

    student_id = student_factory(tutor_id=calendar_owner, first_name="Поздний")
    # 23:30 в UTC+04 = 19:30 UTC того же календарного дня.
    late = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 12, 19, 30),
    )

    with SessionLocal() as db:
        rows = week_lessons(
            db, calendar_owner, date(2026, 10, 12), _tutor("Europe/Ulyanovsk")
        )

    assert [row.lesson.id for row in rows] == [late]


def test_calendar_renders_late_lesson_on_monday(
    client, tutor_factory, student_factory
):
    """Урок 23:30 местного рендерится в понедельнике недели, не в воскресенье."""
    tutor_id = tutor_factory(
        email="cal-tz-plus4@example.com",
        password=PASSWORD,
        timezone="Europe/Ulyanovsk",
    )
    client.post(
        "/tutor/login",
        data={"email": "cal-tz-plus4@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    student_id = student_factory(tutor_id=tutor_id, first_name="Поздний")
    lesson_id = _insert_lesson(
        tutor_id, student_id=student_id,
        starts_at=datetime(2026, 10, 12, 19, 30), duration_min=30,
    )

    page = client.get("/tutor/calendar?start=2026-10-12").text

    card = _card(page, lesson_id)
    assert 'data-date="2026-10-12"' in card
    # Конец урока за полночь прижимается к 23:59 — карточка не должна
    # показывать отрицательный интервал по минутам суток.
    assert "23:30 – 23:59" in card


def test_calendar_today_differs_by_tutor_zone_at_same_moment(
    client, tutor_factory, monkeypatch
):
    """Спека (задача 7.3): «сегодня» считается в зоне педагога.

    При одном и том же серверном моменте (22:30 UTC) для репетитора в
    UTC+04 это уже следующие сутки, а для репетитора в UTC−05 — нет.
    """
    fixed = datetime(2026, 10, 25, 22, 30, tzinfo=UTC)
    monkeypatch.setattr(
        "app.common.services.tutor_time.utcnow", lambda: fixed
    )

    page_by_zone = {}
    for email, zone in (
        ("cal-today-east@example.com", "Europe/Ulyanovsk"),
        ("cal-today-west@example.com", "America/New_York"),
    ):
        tutor_id = tutor_factory(
            email=email, password=PASSWORD, timezone=zone
        )
        client.post(
            "/tutor/login",
            data={"email": email, "password": PASSWORD},
            follow_redirects=False,
        )
        page = client.get("/tutor/calendar").text
        page_by_zone[zone] = (
            tutor_id,
            re.search(r'data-now="([^"]*)"', page).group(1),
            re.search(r'id="calendar-swap"[^>]*?hx-get="([^"]*)"', page, re.S)
            .group(1),
        )

    east = page_by_zone["Europe/Ulyanovsk"]
    west = page_by_zone["America/New_York"]

    # Момент 25.10 22:30 UTC: на востоке UTC+04 это уже 26.10 02:30,
    # на западе EDT (UTC−4) — ещё 25.10 18:30 того же дня.
    assert east[1].startswith("2026-10-26T02:30")
    assert west[1].startswith("2026-10-25T18:30")
    # Открытая неделя — та, к которой относится локальное сегодня:
    # 26.10 (понедельник) открывает неделю 26.10, 25.10 (воскресенье) —
    # неделю 19.10.
    assert "start=2026-10-26" in east[2]
    assert "start=2026-10-19" in west[2]


def test_calendar_swap_carries_server_now(client):
    """Спека (задача 7.4): `#calendar-swap` отдаёт локальный момент сервера."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")

    swap = re.search(r'<div id="calendar-swap"[^>]*>', response.text, re.S)
    assert swap, "контейнер #calendar-swap не найден"
    now_attr = re.search(r'data-now="([^"]*)"', swap.group(0))
    assert now_attr, "у #calendar-swap нет data-now"
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", now_attr.group(1))


def test_calendar_js_today_uses_server_now_not_device_clock():
    """Спека (задача 7.4): `todayIso()`/`prefillMoment()` читают `data-now`.

    Часы устройства не используются: педагог мог открыть календарь с
    устройства в другой зоне, и «сегодня» разошлось бы с неделей,
    которую отрисовал сервер (design.md D7).
    """
    js = _calendar_js()

    today = re.search(
        r"function todayIso\(\) \{(.*?)\n  \}", js, re.S
    )
    assert today, "в calendar.js нет todayIso"
    assert "new Date(" not in today.group(1)
    assert "serverNowParts()" in today.group(1)

    prefill = re.search(
        r"prefillMoment: function \(\) \{(.*?)\n        \},", js, re.S
    )
    assert prefill, "в calendar.js нет prefillMoment"
    assert "new Date(" not in prefill.group(1)
    assert "serverNowParts()" in prefill.group(1)


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
        rows = week_lessons(db, calendar_owner, date(2026, 10, 12), _tutor())

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
            tutor=_tutor(),
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
    # Событие несёт aware UTC — источник истины для «прошло/просрочен»
    # (design D4); при зоне UTC локальные поля совпадают с хранимыми.
    assert event.starts_at == datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
    assert event.ends_at == datetime(2026, 10, 14, 14, 50, tzinfo=UTC)


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
    """2.5: «просрочен» — запланированный урок, чьё время уже прошло.

    Сравнение строится на aware UTC (`starts_at`/`ends_at` против `now`):
    результат не зависит от часов устройства (design D4, задача 7.2).
    """
    from app.calendar.services.presentation import is_overdue
    from app.calendar.services.schedule_event import ScheduleEvent

    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    planned_past = ScheduleEvent(
        starts_at=datetime(2026, 10, 21, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 10, 21, 10, 40, tzinfo=UTC),
        day=date(2026, 10, 21), start=time(10, 0), end=time(10, 40),
        lesson_id="a", status="planned",
    )
    planned_future = ScheduleEvent(
        starts_at=datetime(2026, 10, 21, 13, 0, tzinfo=UTC),
        ends_at=datetime(2026, 10, 21, 13, 40, tzinfo=UTC),
        day=date(2026, 10, 21), start=time(13, 0), end=time(13, 40),
        lesson_id="b", status="planned",
    )
    completed_past = ScheduleEvent(
        starts_at=datetime(2026, 10, 21, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 10, 21, 10, 40, tzinfo=UTC),
        day=date(2026, 10, 21), start=time(10, 0), end=time(10, 40),
        lesson_id="c", status="completed", is_completed=True,
    )

    assert is_overdue(planned_past, now=now) is True
    assert is_overdue(planned_future, now=now) is False
    assert is_overdue(completed_past, now=now) is False


def test_is_past_compares_aware_utc_not_local_wall_time():
    """Спека (задача 7.2): признак «прошло» не зависит от часов устройства.

    Урок начался в 06:00 UTC — это 10:00 настенного у педагога в UTC+04.
    В 08:00 UTC урок уже идёт, хотя по локальным часам карточки (10:00)
    он выглядел бы будущим. Флаг обязан следовать aware-моменту, иначе
    приглушение зависело бы от того, в каком кадре собраны значения.
    """
    from app.calendar.services.presentation import build_event_view
    from app.calendar.services.schedule_event import ScheduleEvent

    event = ScheduleEvent(
        starts_at=datetime(2026, 10, 21, 6, 0, tzinfo=UTC),
        ends_at=datetime(2026, 10, 21, 6, 40, tzinfo=UTC),
        day=date(2026, 10, 21), start=time(10, 0), end=time(10, 40),
        lesson_id="aware", status="planned",
    )

    # 08:00 UTC — после начала урока, хотя локальное 10:00 ещё «впереди».
    started = build_event_view(
        event, now=datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
    )
    assert started["is_past"] is True

    # 05:00 UTC — до начала: урок ещё не начался ни по UTC, ни по локали.
    upcoming = build_event_view(
        event, now=datetime(2026, 10, 21, 5, 0, tzinfo=UTC)
    )
    assert upcoming["is_past"] is False


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


def test_calendar_empty_week_shows_explanation(client, calendar_owner, student_factory):
    """2.6: пустая неделя — пояснение, сетка и шапка на месте, карточек нет.

    Уроки у репетитора есть, но на другой неделе — запрошенная остаётся
    пустой, и страница отдаёт пояснение вместо карточек занятий.
    """
    student_id = student_factory(tutor_id=calendar_owner, first_name="Иван")
    _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2026, 10, 14, 14, 0),
    )

    response = client.get("/tutor/calendar?start=2026-11-09")

    assert response.status_code == 200
    assert "свободная неделя" in response.text
    assert "cal-dayhead" in response.text
    assert "cal-times" in response.text
    # Карточек занятий нет: серверный блок — `class="cal-event"` или
    # `class="cal-event cal-event--past"`; классы `cal-event__*` из
    # inert-шаблона рендерера карточек карточками не считаются.
    assert not re.search(r'class="cal-event[\s"]', response.text)


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

    # Конец жеста вызывает сохранение, передавая карточку, новое начало и
    # признак подтверждения (пустой, если день доступен).
    end = js[js.index("onDragEnd: function"):js.index("moveLesson: function")]
    assert "this.moveLesson(card, newMin" in end

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
    `setCardTitle` — рендер карточки на клиенте удалён вместе с демо-слоем,
    поэтому подсказку обновляет только перенос.
    """
    js = _calendar_js()

    assert "setCardTitle: function" in js
    end = js[js.index("onDragEnd: function"):js.index("moveLesson: function")]
    assert "this.setCardTitle(card, newMin, drag.duration)" in end


# --------------------------------------------------------------------------
# Замена демо-тестов уроков тестами реальных данных (задача 6.1)
# --------------------------------------------------------------------------

def test_calendar_real_lessons_fill_weekdays_only(
    client, calendar_owner, student_factory
):
    """Уроки БД раскладываются по своим дням, включая субботу.

    Заменяет демо-тест «будни расписаны, выходные свободны»: расписание
    теперь приходит из БД, а выходные задаёт репетитор отметками — поэтому
    суббота без отметки ничем не отличается от будня. Отсутствие
    автоматических выходных проверяет
    `test_calendar_week_without_marks_has_no_weekend_automation`.
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


# --------------------------------------------------------------------------
# 9. Окна для записи в сетке (change slots-and-bookings, раздел 7):
#    недельная выборка окон, общий список events, раскладка наложения,
#    состояние окна в событии
# --------------------------------------------------------------------------

FUTURE_MONDAY = date(2099, 2, 2)  # понедельник; 2026-10-23 уже «прошло»



def _week_days(tutor_id: str, monday: date = FUTURE_MONDAY):
    """Дни недели через сервис, без HTTP (зона UTC)."""
    from app.calendar.services.week_days import build_week_days
    from app.database import SessionLocal

    with SessionLocal() as db:
        return build_week_days(db, tutor_id, monday, _tutor())


def _slot_event(days, slot_id: str):
    """Событие окна по его id (None — окна в неделе нет)."""
    for day in days:
        for event in day.events:
            if event.slot_id == slot_id:
                return event
    return None


def test_build_week_days_includes_slot_events(calendar_owner, slot_factory):
    """7.1: окно недели попадает в `day.events` событием с `kind="slot"`.

    Вид задан явно (design D5): пустой `lesson_id` больше ничего не
    означает, поэтому признак окна — отдельное поле `kind`.
    """
    slot_id = slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0))

    days = _week_days(calendar_owner)
    event = _slot_event(days, slot_id)

    assert event is not None, "Окна нет в событиях недели"
    assert event.kind == "slot"
    assert event.is_slot is True
    assert event.slot_state == "free"
    assert event.lesson_id == ""
    # Локальные поля нужны раскладке: 10:00–10:40 в зоне UTC.
    assert (event.day, event.start, event.end) == (
        date(2099, 2, 3), time(10, 0), time(10, 40)
    )
    # Цель и цена у окна пустые: оно не раскрывает, кто занял время.
    assert (event.student, event.price) == ("", 0)


def test_build_week_days_keeps_lessons_and_slots_in_one_list(calendar_owner, student_factory, slot_factory):
    """7.1: уроки и окна лежат в общем списке событий одного дня (design D5)."""
    student_id = student_factory(tutor_id=calendar_owner, first_name="Оба")
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 3, 12, 0),
    )
    slot_id = slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0))

    tuesday = next(day for day in _week_days(calendar_owner) if day.date == date(2099, 2, 3))
    kinds = {event.kind for event in tuesday.events}
    ids = {event.lesson_id for event in tuesday.events} | {
        event.slot_id for event in tuesday.events
    }

    assert kinds == {"lesson", "slot"}
    assert {lesson_id, slot_id} <= ids


def test_build_week_days_excludes_foreign_slots(calendar_owner, tutor_factory, slot_factory):
    """7.1: окно другого репетитора в неделю не попадает."""
    stranger_id = tutor_factory(email="slot-stranger-week@example.com")
    foreign_slot = slot_factory(stranger_id, starts_at=datetime(2099, 2, 3, 11, 0))

    days = _week_days(calendar_owner)

    assert _slot_event(days, foreign_slot) is None


def test_build_week_days_slot_state_is_computed(calendar_owner, student_factory, slot_factory):
    """7.1: состояние окна в событии считается пересечением (design D4).

    Урок 10:20–11:00 пересекает окно 10:00–10:40 → `lesson`; окно
    12:00–12:40 ни с чем не пересекается → `free`.
    """
    student_id = student_factory(tutor_id=calendar_owner, first_name="Занял")
    _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 3, 10, 20), duration_min=40,
    )
    busy_slot = slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0))
    free_slot = slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 12, 0))

    days = _week_days(calendar_owner)

    assert _slot_event(days, busy_slot).slot_state == "lesson"
    assert _slot_event(days, free_slot).slot_state == "free"


def test_layout_events_overlaps_slot_with_lesson(calendar_owner, student_factory, slot_factory):
    """7.1: окно и урок раскладываются как два пересекающихся урока.

    Одна реализация раскладки на общий список `events` — иначе окно
    14:00 нарисовалось бы поверх урока 14:20 (design D5).
    """
    from app.calendar.services.presentation import layout_events

    student_id = student_factory(tutor_id=calendar_owner, first_name="Наложение")
    _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 3, 10, 20), duration_min=40,
    )
    slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0))

    days = _week_days(calendar_owner)
    tuesday = next(day for day in days if day.date == date(2099, 2, 3))
    views = layout_events(
        tuesday.events, now=datetime(2099, 1, 1, 12, 0, tzinfo=UTC)
    )

    assert len(views) == 2
    # Окно идёт первым (10:00), урок — вторым: каждый получает половину.
    assert [view["left_pct"] for view in views] == ["0%", "50%"]
    assert [view["width_pct"] for view in views] == ["50%", "50%"]


def test_calendar_empty_week_with_only_slots_is_not_free(client, calendar_owner, slot_factory):
    """7.1: неделя только из окон — не «свободная неделя» (спека calendar)."""
    slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0))

    page = client.get("/tutor/calendar?start=2099-02-02").text

    assert "свободная неделя" not in page


def test_calendar_slot_card_opens_slot_dialog(client, calendar_owner, slot_factory):
    """7.3: карточка окна несёт `data-slot-id` и открывает диалог окна.

    Клик по карточке ведёт в `#modal` на `GET /tutor/slots/{id}` — форму
    урока окно не открывает (спека calendar, «Окно не открывает форму
    урока»). Раскладка при этом общая с уроками: окно получает те же
    `--top/--dur/--left/--width`.
    """
    slot_id = slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0))

    page = client.get("/tutor/calendar?start=2099-02-02").text
    card = re.search(
        r'<div class="cal-event[^"]*"[^>]*data-slot-id="' + re.escape(slot_id) + r'".*?</div>',
        page,
        re.S,
    )
    assert card, "Карточки окна нет в сетке"
    markup = card.group(0)

    assert 'class="cal-event cal-event--slot cal-event--slot-free"' in markup
    assert f'hx-get="/tutor/slots/{slot_id}"' in markup
    assert 'hx-target="#modal"' in markup
    # Форма урока к окну не привязана.
    assert "/edit" not in markup
    assert "data-lesson-id" not in markup
    # Позиция и размер считаются той же раскладкой, что у урока.
    for marker in ("--top:", "--dur:", "--left:", "--width:"):
        assert marker in markup, marker
    # Состояние окна доступно и разметке, и стилям.
    assert 'data-slot-state="free"' in markup
    assert "Свободно" in markup
    assert "10:00 – 10:40" in markup
    # Свободное окно не приглушается: место ещё можно занять.
    assert "cal-event--muted" not in markup

    # Диалог окна по этому адресу отдаётся сервером.
    dialog = client.get(f"/tutor/slots/{slot_id}")
    assert dialog.status_code == 200
    assert "Окно для записи" in dialog.text
    assert 'id="slot-dialog"' in dialog.text


def test_calendar_slot_saved_refreshes_week(client):
    """7.3: `slot-saved` перерисовывает неделю с сервера.

    Создание, правка, удаление окна и действия с бронью отвечают
    `HX-Trigger: slot-saved`; подписка живёт на `#calendar-swap`, поэтому
    новая карточка появляется без перезагрузки страницы.
    """
    _login(client)
    page = client.get("/tutor/calendar?start=2026-10-12").text

    swap = re.search(r'<div id="calendar-swap".*?>', page, re.S)
    assert swap, "Область #calendar-swap не найдена"
    assert "slot-saved from:body" in swap.group(0)

    # Скрипт диалога окна подключён до Alpine — иначе `alpine:init`
    # пройдёт раньше подписки на `slotDialog` (правило AGENTS.md).
    assert page.index("/static/slots.js") < page.index("/static/alpine.min.js")


def test_slot_dialog_links_to_lesson_form_with_duration(client, calendar_owner, slot_factory):
    """7.4: «Записать ученика» несёт `?starts_at=` и `&duration_min=`.

    Ссылка ведёт в настоящую форму урока (не в клиентскую модалку):
    дата и время — настенные значения окна, длительность — его
    `duration_min`. Иначе созданный урок разошёлся бы с окном по времени
    и окно осталось бы «Свободно» (спека calendar, «Префилл из окна»).
    """
    slot_id = slot_factory(
        calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0), duration_min=40
    )

    dialog = client.get(f"/tutor/slots/{slot_id}").text
    link = re.search(r'<button[^>]*data-slot-book[^>]*>', dialog, re.S)
    assert link, "Кнопки «Записать ученика» нет в диалоге окна"
    url = re.search(r'hx-get="([^"]+)"', link.group(0)).group(1)

    assert url.startswith("/tutor/lessons/new?")
    assert "starts_at=2099-02-03T10:00" in url
    assert "duration_min=40" in url
    assert 'hx-target="#modal"' in link.group(0)


def test_lesson_form_prefills_duration_from_slot(
    client, calendar_owner, student_factory
, slot_factory):
    """7.4: форма урока показывает длительность окна и сохраняется без ошибки.

    Значение из `?duration_min=` выделено в селекте; сохранение той же
    формы создаёт урок ровно на длительность окна — окно становится
    «Занято уроком», а не остаётся свободным рядом с уроком.
    """
    student_id = student_factory(tutor_id=calendar_owner, first_name="Из окна")

    form = client.get(
        "/tutor/lessons/new?starts_at=2099-02-03T10:00&duration_min=40"
    ).text
    # «Начало» и «Длительность» предзаполнены из окна.
    assert 'value="2099-02-03T10:00"' in form
    duration_option = re.search(
        r'<option value="40"[^>]*selected[^>]*>', form
    )
    assert duration_option, "Длительность окна не выделена в селекте"

    response = client.post(
        "/tutor/lessons",
        data={
            "type": "individual",
            "student_id": student_id,
            "starts_at": "2099-02-03T10:00",
            "duration_min": "40",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "lesson-saved"
    # Ошибок валидации в ответе нет: тело пустое — модалка закрывается.
    assert response.text == ""

    from app.database import SessionLocal
    from app.lesson.models.lesson import Lesson

    with SessionLocal() as db:
        lesson = db.query(Lesson).filter_by(student_id=student_id).one()
        assert lesson.duration_min == 40

    # Окно на это время больше не «Свободно» (спека calendar, «Окно занято
    # после урока»): состояние считается пересечением, а не хранится.
    slot_id = slot_factory(
        calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0), duration_min=40
    )
    event = _slot_event(_week_days(calendar_owner), slot_id)
    assert event is not None
    assert event.slot_state == "lesson"


def test_lesson_form_ignores_unknown_duration(client, calendar_owner):
    """7.4: длительность вне `LESSON_DURATIONS` игнорируется, форма открыта.

    Префилл — удобство, а не источник истины: 80 минут нет в закрытом
    списке, поэтому селект остаётся на значении по умолчанию.
    """
    form = client.get(
        "/tutor/lessons/new?starts_at=2099-02-03T10:00&duration_min=80"
    ).text

    assert "Новый урок" in form
    assert not re.search(r'<option value="80"', form)


def test_calendar_public_link_points_to_public_page(client, calendar_owner):
    """7.5: «Ссылка на окна» копирует публичный адрес недели, а не календарь.

    База ссылки (`/s/<tutor_id>`) приходит с сервера в `data-public-url`
    корня, понедельник дописывает `calendar.js` из видимой сетки. Адрес
    календаря (`/tutor/calendar`) в ссылку не попадает: ученик не вошёл
    в систему, и такая ссылка вела бы его на форму входа (design D7).
    """
    from app.slot.services.public_link import PUBLIC_PREFIX

    page = client.get("/tutor/calendar?start=2026-10-12").text

    root = re.search(r'<div id="calendar-swap"[^>]*>', page, re.S)
    assert root, "Корня #calendar-swap нет в разметке"
    public = re.search(r'data-public-url="([^"]+)"', root.group(0))
    assert public, "У корня нет data-public-url"
    assert public.group(1) == f"{PUBLIC_PREFIX}/{calendar_owner}"

    js = _calendar_js()
    builder = js[js.index("publicWeekUrl: function"):js.index("copyWeekLink: function")]
    # Адрес собирается из базы и понедельника видимой недели.
    assert "this.publicBase()" in builder
    assert "this.currentStart()" in builder
    assert '"?start=" + start' in builder
    # Режим раскраски в публичную ссылку не попадает.
    assert "withColor" not in builder

    # Копирование не обещает успех заранее: тост — только в обработчике
    # успешной записи, при отказе показывается поле со ссылкой.
    copier = js[js.index("copyWeekLink: function"):js.index("showToast: function")]
    assert "navigator.clipboard.writeText(url).then(" in copier
    assert "self.linkFallback.open = true" in copier
    assert "showFallback" in copier


def _slot_card(page: str, slot_id: str) -> str:
    """Разметка карточки окна по её data-slot-id (пустая строка — нет)."""
    match = re.search(
        r'<div class="cal-event[^"]*"[^>]*data-slot-id="' + re.escape(slot_id) + r'".*?</div>',
        page,
        re.S,
    )
    return match.group(0) if match else ""



def test_calendar_lesson_slot_card_is_muted(client, calendar_owner, student_factory, slot_factory):
    """7.2: окно, занятое уроком, показывает «Занято уроком» и приглушено.

    Состояние считается пересечением с уроком, а не хранится (design D4),
    поэтому удаление урока возвращает окно в «Свободно».
    """
    from app.database import SessionLocal
    from app.lesson.models.lesson import Lesson

    student_id = student_factory(tutor_id=calendar_owner, first_name="Занял")
    lesson_id = _insert_lesson(
        calendar_owner, student_id=student_id,
        starts_at=datetime(2099, 2, 3, 10, 20), duration_min=40,
    )
    slot_id = slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0))

    card = _slot_card(client.get("/tutor/calendar?start=2099-02-02").text, slot_id)

    assert "Занято уроком" in card
    assert "cal-event--muted" in card
    assert "cal-event--slot-lesson" in card
    assert "Свободно" not in card

    # Урок удалён — окно снова свободно (состояние не хранится).
    with SessionLocal() as db:
        db.delete(db.get(Lesson, lesson_id))
        db.commit()

    freed = _slot_card(client.get("/tutor/calendar?start=2099-02-02").text, slot_id)
    assert "Свободно" in freed
    assert "cal-event--muted" not in freed


def test_calendar_pending_and_booked_slot_cards(client, calendar_owner, slot_factory, booking_factory):
    """7.2: «Ожидает подтверждения» и «Занято записью» — разные подписи.

    Приоритет `booking > lesson > past > free` (design D4): подтверждённая
    бронь важнее прошедшего времени, ожидающая — тоже занятое окно.
    """
    pending_slot = slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0))
    booked_slot = slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 12, 0))
    booking_factory(pending_slot, status="pending")
    booking_factory(booked_slot, status="confirmed")

    page = client.get("/tutor/calendar?start=2099-02-02").text

    pending = _slot_card(page, pending_slot)
    assert "Ожидает подтверждения" in pending
    assert "cal-event--slot-pending" in pending
    # Ожидающая бронь ещё не закреплена за учеником — не приглушается.
    assert "cal-event--muted" not in pending

    booked = _slot_card(page, booked_slot)
    assert "Занято записью" in booked
    assert "cal-event--slot-booking" in booked
    assert "cal-event--muted" in booked


def test_calendar_past_slot_card_shows_past_state(client, calendar_owner, slot_factory):
    """7.2: прошедшее окно — «Время прошло» и приглушение.

    Прошедшее окно не предлагается ученику на публичной странице, но в
    календаре педагога остаётся: он видит, что время ушло (спека calendar).
    """
    slot_id = slot_factory(calendar_owner, starts_at=datetime(2020, 1, 8, 10, 0))

    card = _slot_card(client.get("/tutor/calendar?start=2020-01-06").text, slot_id)

    assert card, "Карточки прошедшего окна нет в сетке"
    assert "Время прошло" in card
    assert "cal-event--muted" in card
    assert "cal-event--slot-past" in card


def test_calendar_slot_dots_and_count_include_slots(client, calendar_owner, slot_factory):
    """7.2: шапка дня считает окна наравне с уроками.

    Точка окна окрашена токеном `--cal-slot-accent`, а не цветом цели:
    окно не принадлежит ученику (спека calendar).
    """
    from app.calendar.services.presentation import SLOT_ACCENT

    slot_factory(calendar_owner, starts_at=datetime(2099, 2, 3, 10, 0))

    page = client.get("/tutor/calendar?start=2099-02-02").text

    assert SLOT_ACCENT in page
    assert "1 урок" in page
