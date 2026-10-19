"""Тесты календаря: unit-тесты демо-генератора и страницы GET /tutor/calendar.

Имена unit-тестов генератора содержат «demo», чтобы их можно было отобрать
фильтром `uv run pytest tests/test_calendar.py -k demo`.
"""

import re
from datetime import date, time
from pathlib import Path

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
    for label in ("Сегодня", "Добавить", "Ссылка на окна", "Цвет: ученик"):
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


def test_calendar_weekend_badge(client):
    """Сб/вс отмечены плашкой «Выходной»; будни — числами занятий."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "Выходной" in response.text
    assert "2 урока" in response.text  # понедельник демо-недели


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
# 3.3 Карточки demo-занятий и состояние сетки
# --------------------------------------------------------------------------

def test_calendar_event_card_content(client):
    """Карточка урока: имя с ценой и интервал времени вида «14:00 – 14:40»."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "Иван И." in response.text
    assert "14:00 – 14:40" in response.text  # среда демо-недели


def test_calendar_overlapping_events_shifted(client):
    """Пересекающиеся уроки среды накладываются со сдвигом (left/width)."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    # Оба урока присутствуют, у первого и второго разные смещения/ширины.
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


def test_calendar_empty_week_renders(client):
    """Новогодний перерыв: страница без ошибки, пояснение о свободной неделе."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-12-28")
    assert response.status_code == 200
    assert "свободная неделя" in response.text
    # Карточек занятий нет: серверный блок — `class="cal-event"` или
    # `class="cal-event cal-event--past"`; классы `cal-event__*` из
    # inert-шаблона рендерера карточек карточками не считаются.
    assert not re.search(r'class="cal-event[\s"]', response.text)


def test_calendar_past_events_dimmed(client):
    """Прошедшие уроки приглушены классом cal-event--past."""
    _login(client)
    # Неделя 12–18 октября 2026 целиком в прошлом (тесты пишутся 2026-10-19).
    past = client.get("/tutor/calendar?start=2026-10-12")
    assert 'class="cal-event cal-event--past"' in past.text
    # Неделя далеко в будущем (февраль — вне отпуска и перерыва) —
    # ни один урок не «прошедший».
    future = client.get("/tutor/calendar?start=2099-02-02")
    assert "cal-event" in future.text  # уроки есть
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
    """Кнопки недель и «Сегодня» листают через hx-get с hx-target на область."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert 'hx-get="/tutor/calendar?start=2026-10-05"' in response.text  # назад
    assert 'hx-get="/tutor/calendar?start=2026-10-19"' in response.text  # вперёд
    assert 'hx-get="/tutor/calendar"' in response.text  # «Сегодня»
    assert response.text.count('hx-target="#calendar-swap"') >= 3


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

def test_calendar_modal_present_with_fields(client):
    """Модалка в разметке: выбор ученика (dropdown), длительность 40, кнопки."""
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert "Новый урок" in response.text
    # Dropdown учеников собран из демо-учеников.
    assert 'id="cal-student"' in response.text
    assert '<option value="Иван И.">Иван И.</option>' in response.text
    # Длительность по умолчанию — 40 минут; предмета в форме нет.
    duration = re.search(r'id="cal-duration"[^>]*', response.text)
    assert duration, "Поля длительности нет в разметке"
    assert 'value="40"' in duration.group(0)
    assert "Предмет" not in response.text
    # Кнопки формы.
    assert ' @click="closeModal()">Отмена</button>' in response.text
    assert ' @click="saveLesson()">Сохранить</button>' in response.text


def test_calendar_modal_entry_points_wired(client):
    """Точки входа модалки: клик четверти, «Добавить», мобильная FAB.

    «Сохранить» собирает карточку из общего рендерера `#cal-event-template`.
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

def test_calendar_events_expose_drag_data(client):
    """Карточки уроков несут дату колонки, начало и длительность в минутах.

    Драг в calendar.js читает эти значения и фиксирует новый слот только
    в DOM — без сетевых запросов. Значения: Иван И. в понедельник
    10:00 на 40 минут.
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    card = re.search(
        r'<div class="cal-event[^"]*"\s+data-student="Иван И\.[^"]*"\s+'
        r'data-date="2026-10-12"\s+data-start-min="600"\s+'
        r'data-duration-min="40"',
        response.text,
    )
    assert card, "У карточки урока нет данных для drag"
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


def test_demo_recurrence_same_weekday_same_lessons():
    """Один день недели → одинаковое занятие на разных неделях."""
    this_week = build_week(_PLAIN_MONDAY)
    three_weeks_later = build_week(date(2026, 11, 2))

    for current, later in zip(this_week, three_weeks_later, strict=True):
        signature = lambda day: [  # noqa: E731
            (e.start, e.end, e.student, e.price, e.color, e.is_group)
            for e in day.lessons
        ]
        assert signature(current) == signature(later)


def test_demo_weekdays_have_lessons_and_weekends_off():
    """Будни расписаны, суббота/воскресенье — выходные без занятий."""
    days = build_week(_PLAIN_MONDAY)
    assert all(day.lessons for day in days[:5])
    assert not any(day.lessons for day in days[5:])
    assert not any(day.is_weekend for day in days[:5])
    assert all(day.is_weekend for day in days[5:])


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


def test_demo_overlapping_lessons_in_one_day():
    """В среде есть пересекающиеся уроки 14:00–14:40 и 14:20–15:00."""
    days = build_week(_PLAIN_MONDAY)
    wednesday = days[2]
    assert wednesday.date.weekday() == 2
    by_start = {event.start: event for event in wednesday.lessons}
    first, second = by_start[time(14, 0)], by_start[time(14, 20)]
    assert first.end == time(14, 40)
    assert second.end == time(15, 0)


def test_demo_lesson_fields_filled():
    """Урок несёт ученика, цену, длительность и цвет."""
    monday_lessons = build_week(_PLAIN_MONDAY)[0].lessons
    ivan = next(event for event in monday_lessons if event.student == "Иван И.")
    assert ivan.price == 1200
    assert ivan.end == time(10, 40)
    assert ivan.color.startswith("#")
    assert not ivan.is_group
    tuesday = build_week(_PLAIN_MONDAY)[1]
    assert any(event.is_group for event in tuesday.lessons)  # групповое есть


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

    Выбор ученика в режиме «слот» скрыт (x-show на обёртке поля).
    """
    _login(client)
    response = client.get("/tutor/calendar?start=2026-10-12")
    assert 'id="cal-add-slot" @click="openSlotDialog()"' in response.text
    assert "Добавить слот" in response.text
    # Заголовок диалога переключается на «Новый слот» (режим modal.mode).
    assert "Новый слот" in response.text
    # Редактируемые дата и время: шаг 900 с = граница четверти часа.
    date_input = re.search(r'id="cal-slot-date"[^>]*', response.text)
    assert date_input, "Поля даты слота нет в разметке"
    assert 'type="date"' in date_input.group(0)
    time_input = re.search(r'id="cal-slot-time"[^>]*', response.text)
    assert time_input, "Поля времени слота нет в разметке"
    assert 'type="time"' in time_input.group(0)
    assert 'step="900"' in time_input.group(0)
    # Кнопка «Создать» вызывает createSlot; выбор ученика скрыт в режиме слота.
    assert '@click="createSlot()">Создать</button>' in response.text
    student_field = re.search(r'<div[^>]*id="cal-student-field"[^>]*>', response.text)
    assert student_field, "Обёртка поля «Ученик» не найдена"
    assert "modal.mode !== 'slot'" in student_field.group(0)


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

    Данные живут только в DOM-атрибутах (data-contact/title) — без БД,
    localStorage и сетевых запросов.
    """
    js = _calendar_js()
    assert 'card.setAttribute("title"' in js
    assert 'card.setAttribute("data-contact"' in js
    assert "localStorage" not in js


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
