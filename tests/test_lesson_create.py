"""Создание урока (5.1–5.2): модальная форма, валидация, генерация серии.

HTTP-клиент проходит тот же путь, что и браузер: GET фрагмента модалки,
POST формы (с заголовком htmx — так отвечает успех: пустое тело + HX-Trigger).
Предзаполнение панели расписания (JS) проверяется по исходнику компонента —
браузерных тестов в проекте нет.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_series import LessonSeries

PASSWORD = "Секретный-Пароль-1"
ROOT = Path(__file__).resolve().parent.parent
LESSONS_JS = (ROOT / "app" / "static" / "lessons.js").read_text(encoding="utf-8")
HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="lessons-create@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "lessons-create@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _all_lessons() -> list[dict]:
    """Все уроки БД по времени начала (значения, а не ORM-объекты)."""
    with SessionLocal() as db:
        lessons = db.scalars(select(Lesson).order_by(Lesson.starts_at)).all()
        return [
            {
                "id": lesson.id,
                "student_id": lesson.student_id,
                "group_id": lesson.group_id,
                "series_id": lesson.series_id,
                "type": lesson.type,
                "starts_at": lesson.starts_at,
                "duration_min": lesson.duration_min,
                "note": lesson.note,
                "meeting_url": lesson.meeting_url,
                "price": lesson.price,
                "status": lesson.status,
                "rating": lesson.rating,
                "family_comment": lesson.family_comment,
            }
            for lesson in lessons
        ]


def _all_series() -> list[dict]:
    """Все серии БД."""
    with SessionLocal() as db:
        series = db.scalars(select(LessonSeries)).all()
        return [
            {
                "id": item.id,
                "slots": item.slots,
                "interval_weeks": item.interval_weeks,
                "until_date": item.until_date,
            }
            for item in series
        ]


def _form(student_id: str, **extra) -> dict:
    """Валидная форма индивидуального урока (понедельник 19.10.2026)."""
    data = {
        "type": "individual",
        "student_id": student_id,
        "starts_at": "2026-10-19T10:00",
        "duration_min": "60",
    }
    data.update(extra)
    return data


def _slots_json(*slots) -> str:
    """Слоты формы: `slots` — JSON-список объектов D1 одним полем."""
    return json.dumps(
        [
            {"weekday": weekday, "start_time": start, "end_time": end}
            for weekday, start, end in slots
        ]
    )


# --------------------------------------------------------------------------
# 5.1 Форма и POST-обработчик
# --------------------------------------------------------------------------


def test_new_lesson_form_requires_session(client):
    """Без входа фрагмент модалки не отдаётся — редирект на вход."""
    response = client.get("/tutor/lessons/new", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_new_lesson_form_renders(owner, client):
    """Модалка «Новый урок»: вкладки, поля, кнопки и отсутствие лишних полей."""
    page = client.get("/tutor/lessons/new").text

    assert "Новый урок" in page

    # Вкладки: «Урок» активна, «ДЗ» — видимая, но неактивная заглушка
    # с подсказкой: клик не активирует её, панели ДЗ нет (спека).
    hw_tab = re.search(r'<button class="tab tab--disabled"[^>]*>', page)
    assert hw_tab is not None
    assert 'id="lesson-tab-hw"' in hw_tab.group(0)
    assert "disabled" in hw_tab.group(0)
    assert 'title="Домашнее задание задаётся после урока"' in hw_tab.group(0)
    assert "panel-hw" not in page  # панели ДЗ нет
    assert 'name="assignment"' not in page  # полей ДЗ в создании нет
    assert "Сохранить ДЗ" not in page

    # Поля создания (спека «Создание урока»).
    for marker in (
        'name="student_id"',
        'name="group_id"',
        'name="note"',
        'name="meeting_url"',
        'name="starts_at"',
        'name="duration_min"',
        'name="repeat"',
        'name="type"',
        'name="price"',
    ):
        assert marker in page, marker
    assert "Начало *" in page
    assert "Повторять урок" in page
    assert "Оплата ученика" in page
    assert ">Закрыть</button>" in page
    assert ">Сохранить</button>" in page

    # Тип «Групповой» прячет оплату и переключает цель (Alpine-выражения).
    assert "type !== 'group'" in page
    assert "type === 'group'" in page

    # Поля редактирования в создании отсутствуют.
    for absent in (
        'name="status"',
        'name="rating"',
        'name="family_comment"',
        'name="series_all"',
    ):
        assert absent not in page, absent


def test_new_lesson_form_start_time_controls(owner, client):
    """Поле «Начало» управляет формой (см. app/static/lessons.js): подсказка
    об окончании урока, минуты 00 при открытии пикера и блокировка
    «Повторять урок» / «Добавить время», пока время не указано."""
    page = client.get("/tutor/lessons/new").text

    starts = re.search(r'<input class="input" id="lesson-starts-at".*?>', page, re.S)
    assert starts is not None
    assert '@input="onStartInput($event.target.value)"' in starts.group(0)
    assert '@focus="onStartFocus()"' in starts.group(0)
    assert '@blur="onStartBlur()"' in starts.group(0)

    assert "Урок закончится в " in page
    assert "Сначала укажите начало урока." in page
    assert ':disabled="!startsAt"' in page


def test_new_lesson_form_note_is_four_rows(owner, client):
    """«Заметка к занятию» — четыре строки (высоту задаёт `rows`)."""
    page = client.get("/tutor/lessons/new").text
    note = re.search(r'<textarea[^>]*id="lesson-note"[^>]*>', page)
    assert note is not None
    assert 'rows="4"' in note.group(0)


def test_new_lesson_form_has_no_ignored_fields(owner, client):
    """Спека «Форма урока без игнорируемых полей»: ни одного из них."""
    page = client.get("/tutor/lessons/new").text
    for absent in ("Предмет", "Место", "Оплата учителя", "Учитель"):
        assert absent not in page, absent


def test_create_single_lesson(owner, client, student_factory):
    """Успешное создание: событие закрывает модалку, урок в БД «Запланирован»."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    response = client.post(
        "/tutor/lessons",
        data=_form(
            student,
            note="Подготовка к ОГЭ",
            meeting_url="https://meet.example.com/abc",
            price="1200",
        ),
        headers=HTMX,
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "lesson-saved"
    assert response.text == ""  # пустое тело закрывает модалку свопом

    lessons = _all_lessons()
    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson["student_id"] == student
    assert lesson["type"] == "individual"
    assert lesson["starts_at"] == datetime(2026, 10, 19, 10, 0)
    assert lesson["duration_min"] == 60
    assert lesson["note"] == "Подготовка к ОГЭ"
    assert lesson["meeting_url"] == "https://meet.example.com/abc"
    assert lesson["price"] == 1200
    assert lesson["status"] == "planned"
    assert lesson["series_id"] is None


def test_create_without_htmx_redirects(owner, client, student_factory):
    """Прямая POST-навигация без htmx — редиректом на список."""
    student = student_factory(tutor_id=owner)
    response = client.post(
        "/tutor/lessons", data=_form(student), follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/lessons"


def test_create_requires_start(owner, client, student_factory):
    """Пустое начало: форма показывает ошибку, поле обязательно, урока нет."""
    student = student_factory(tutor_id=owner)
    response = client.post(
        "/tutor/lessons", data=_form(student, starts_at=""), headers=HTMX
    )
    assert response.status_code == 200
    assert "Укажите начало урока." in response.text
    assert re.search(r'name="starts_at"[^>]*required', response.text)
    assert _all_lessons() == []


def test_create_duration_out_of_list(owner, client, student_factory):
    """Длительность вне закрытого списка (80) отклоняется валидацией."""
    student = student_factory(tutor_id=owner)
    response = client.post(
        "/tutor/lessons", data=_form(student, duration_min="80"), headers=HTMX
    )
    assert "Выберите длительность урока из списка." in response.text
    assert _all_lessons() == []


def test_create_target_must_match_type(owner, client, student_factory, group_factory):
    """Цель по типу: групповой → группа, остальные → ученик (спека)."""
    student = student_factory(tutor_id=owner)
    group = group_factory(tutor_id=owner)

    response = client.post(
        "/tutor/lessons", data=_form(student, type="group"), headers=HTMX
    )
    assert "Для группового урока выберите группу, а не ученика." in response.text

    response = client.post(
        "/tutor/lessons",
        data={
            "type": "individual",
            "group_id": group,
            "starts_at": "2026-10-19T10:00",
            "duration_min": "60",
        },
        headers=HTMX,
    )
    assert "Для этого типа урока выберите ученика, а не группу." in response.text

    response = client.post(
        "/tutor/lessons",
        data={"type": "trial", "starts_at": "2026-10-19T10:00", "duration_min": "60"},
        headers=HTMX,
    )
    assert "Выберите ученика для урока." in response.text

    assert _all_lessons() == []


def test_create_group_lesson(owner, client, group_factory):
    """Групповой урок: цель — группа, оплата не принимается (скрыта в форме)."""
    group = group_factory(tutor_id=owner, name="Математика 9А")
    response = client.post(
        "/tutor/lessons",
        data={
            "type": "group",
            "group_id": group,
            "starts_at": "2026-10-21T15:30",
            "duration_min": "90",
        },
        headers=HTMX,
    )
    assert response.status_code == 200

    lesson = _all_lessons()[0]
    assert lesson["group_id"] == group
    assert lesson["student_id"] is None
    assert lesson["price"] is None
    assert lesson["duration_min"] == 90


def test_create_ignores_status_rating_and_subject_fields(
    owner, client, student_factory
):
    """Создание игнорирует статус/оценку/комментарий и поля вне спеки."""
    student = student_factory(tutor_id=owner)
    response = client.post(
        "/tutor/lessons",
        data=_form(
            student,
            subject="Математика",
            place="Онлайн",
            teacher_pay="500",
            tutor=owner,
            status="completed",
            rating="5",
            family_comment="Отлично!",
        ),
        headers=HTMX,
    )
    assert response.status_code == 200

    lesson = _all_lessons()[0]
    assert lesson["status"] == "planned"
    assert lesson["rating"] is None
    assert lesson["family_comment"] is None


def test_create_target_must_belong_to_tutor(owner, client, tutor_factory, student_factory):
    """Чужая цель не принимается: урок нельзя подложить чужому репетитору."""
    other = tutor_factory(email="lessons-create-other@example.com")
    foreign = student_factory(tutor_id=other, first_name="Чужой")
    response = client.post(
        "/tutor/lessons", data=_form(foreign), headers=HTMX
    )
    assert response.status_code == 200
    assert "Ученик не найден." in response.text
    assert _all_lessons() == []


# --------------------------------------------------------------------------
# 5.2 Панель расписания и генерация серии
# --------------------------------------------------------------------------


def test_schedule_panel_prefills_slot_in_js():
    """Предзаполнение слота из «Начало» и «Длительности» — в компоненте JS."""
    assert "prefillSlot" in LESSONS_JS
    assert "lesson-starts-at" in LESSONS_JS
    assert "lesson-duration" in LESSONS_JS
    # Слоты уходят формой одним JSON-полем (решение D1).
    assert "slotsValue" in LESSONS_JS
    assert "start_time" in LESSONS_JS


def test_create_series_mondays(owner, client, student_factory):
    """Все понедельники с 19.10 по 09.11 включительно, одна серия."""
    student = student_factory(tutor_id=owner)
    response = client.post(
        "/tutor/lessons",
        data=_form(
            student,
            repeat="on",
            slots=_slots_json((0, "10:00", "11:00")),
            interval_weeks="1",
            until_date="2026-11-09",
        ),
        headers=HTMX,
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "lesson-saved"

    lessons = _all_lessons()
    assert [lesson["starts_at"] for lesson in lessons] == [
        datetime(2026, 10, 19, 10, 0),
        datetime(2026, 10, 26, 10, 0),
        datetime(2026, 11, 2, 10, 0),
        datetime(2026, 11, 9, 10, 0),
    ]
    series_ids = {lesson["series_id"] for lesson in lessons}
    assert len(series_ids) == 1
    assert None not in series_ids
    assert {lesson["status"] for lesson in lessons} == {"planned"}

    series = _all_series()
    assert len(series) == 1
    assert series[0]["slots"] == [
        {"weekday": 0, "start_time": "10:00", "end_time": "11:00"}
    ]
    assert series[0]["interval_weeks"] == 1
    assert series[0]["until_date"] == date(2026, 11, 9)


def test_create_series_two_slots(owner, client, student_factory):
    """Два слота (Пн 10:00 и Чт 15:00): по два урока в неделю, в своих днях."""
    student = student_factory(tutor_id=owner)
    response = client.post(
        "/tutor/lessons",
        data=_form(
            student,
            repeat="on",
            slots=_slots_json((0, "10:00", "11:00"), (3, "15:00", "16:30")),
            interval_weeks="1",
            until_date="2026-10-29",
        ),
        headers=HTMX,
    )
    assert response.status_code == 200

    lessons = _all_lessons()
    assert [lesson["starts_at"] for lesson in lessons] == [
        datetime(2026, 10, 19, 10, 0),
        datetime(2026, 10, 22, 15, 0),
        datetime(2026, 10, 26, 10, 0),
        datetime(2026, 10, 29, 15, 0),
    ]
    assert len({lesson["series_id"] for lesson in lessons}) == 1


def test_create_repeat_requires_until_date(owner, client, student_factory):
    """Повтор без даты окончания блокирует сохранение (спека)."""
    student = student_factory(tutor_id=owner)
    response = client.post(
        "/tutor/lessons",
        data=_form(
            student,
            repeat="on",
            slots=_slots_json((0, "10:00", "11:00")),
        ),
        headers=HTMX,
    )
    assert "Укажите дату окончания повтора." in response.text
    assert _all_lessons() == []
    assert _all_series() == []


def test_create_repeat_requires_slots(owner, client, student_factory):
    """Пустой список слотов при повторе — ошибка, ничего не создано."""
    student = student_factory(tutor_id=owner)
    response = client.post(
        "/tutor/lessons",
        data=_form(
            student,
            repeat="on",
            slots="[]",
            until_date="2026-11-09",
        ),
        headers=HTMX,
    )
    assert "Панель расписания пуста: добавьте хотя бы один слот." in response.text
    assert _all_lessons() == []
    assert _all_series() == []


# --------------------------------------------------------------------------
# Префилл «Начала» из календаря (change calendar-real-lessons, задача 3.1)
# --------------------------------------------------------------------------

def _starts_input(page: str) -> str:
    """Тег поля «Начало» из разметки формы."""
    match = re.search(r'<input class="input" id="lesson-starts-at".*?>', page, re.S)
    assert match is not None, "Поля «Начало» нет в форме"
    return match.group(0)


def test_new_lesson_form_prefills_start_from_calendar(owner, client):
    """`?starts_at=` заполняет «Начало» (спека «Префилл из календаря»)."""
    page = client.get("/tutor/lessons/new?starts_at=2026-10-15T07:15").text
    assert 'value="2026-10-15T07:15"' in _starts_input(page)


def test_new_lesson_form_ignores_bad_start(owner, client):
    """Некорректный `starts_at` — форма открыта, «Начало» пустое."""
    response = client.get("/tutor/lessons/new?starts_at=abc")
    assert response.status_code == 200
    assert "Новый урок" in response.text
    assert 'value=""' in _starts_input(response.text)
