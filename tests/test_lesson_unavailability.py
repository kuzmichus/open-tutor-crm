"""Предупреждение о постановке урока в отмеченный день (design.md D5, D6).

Проверяется HTTP-путём — те же маршруты и поля формы, что у пользователя:
создание урока и серии, правка «Начала», перенос перетаскиванием, а также
передача признака подтверждения `ack_unavailable`.
"""

import json
import re
from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="lesson-unavail@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "lesson-unavail@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def student(owner, student_factory):
    """Ученик этого репетитора."""
    return student_factory(tutor_id=owner, first_name="Иван")


def _lessons() -> list[Lesson]:
    """Все уроки БД по времени начала."""
    with SessionLocal() as db:
        return list(db.scalars(select(Lesson).order_by(Lesson.starts_at)))


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


def _mark_monday(tutor_id: str, unavailability_factory, **extra):
    """Отметка на понедельник 19.10.2026 (день формы по умолчанию)."""
    values = {"start_date": date(2026, 10, 19), "end_date": date(2026, 10, 19)}
    values.update(extra)
    return unavailability_factory(tutor_id=tutor_id, **values)


# --------------------------------------------------------------------------
# 5.1 Создание урока: без подтверждения урок не создан, с ним — создан
# --------------------------------------------------------------------------


def test_create_lesson_in_marked_day_returns_warning(
    owner, student, client, unavailability_factory
):
    """Без ack форма возвращается с баннером и присланными значениями.

    Предупреждение об одном уроке — в единственном числе, без счётчика
    затронутых занятий: счётчик появляется только у серии.
    """
    _mark_monday(owner, unavailability_factory, reason="vacation")

    response = client.post("/tutor/lessons", data=_form(student), headers=HTMX)

    assert response.status_code == 200
    assert "День отмечен как недоступный: Отпуск." in response.text
    assert "Всё равно поставить урок?" in response.text
    assert "Затронуто занятий" not in response.text
    # Урок ещё не создан.
    assert _lessons() == []
    # Присланные значения вернулись в форму.
    assert 'value="2026-10-19T10:00"' in response.text
    assert "HX-Trigger" not in response.headers


def test_create_lesson_in_marked_day_with_ack_creates_it(
    owner, student, client, unavailability_factory
):
    """С подтверждением урок создаётся обычным порядком."""
    _mark_monday(owner, unavailability_factory, reason="sick")

    response = client.post(
        "/tutor/lessons",
        data=_form(student, ack_unavailable="1"),
        headers=HTMX,
    )

    assert response.status_code == 200
    assert response.text == ""
    assert response.headers["HX-Trigger"] == "lesson-saved"

    (lesson,) = _lessons()
    assert lesson.starts_at == datetime(2026, 10, 19, 10, 0)
    assert lesson.status == "planned"


def test_create_lesson_in_free_day_creates_immediately(
    owner, student, client, unavailability_factory
):
    """Свободный день: предупреждения нет, урок создаётся сразу."""
    _mark_monday(owner, unavailability_factory)  # отметка в другой день
    # Отметка выше — на 19.10, поэтому урок ставим на 20.10.
    response = client.post(
        "/tutor/lessons",
        data=_form(student, starts_at="2026-10-20T10:00"),
        headers=HTMX,
    )

    assert response.text == ""
    assert response.headers["HX-Trigger"] == "lesson-saved"
    assert len(_lessons()) == 1


def test_create_series_warns_once_with_affected_count(
    owner, student, client, unavailability_factory
):
    """Серия: одно предупреждение с числом занятий, попавших в отметку."""
    # Отметка покрывает 19.10–02.11: из четырёх понедельников серии
    # (19.10, 26.10, 02.11, 09.11) затронуты три.
    unavailability_factory(
        tutor_id=owner,
        start_date=date(2026, 10, 19),
        end_date=date(2026, 11, 2),
    )

    response = client.post(
        "/tutor/lessons",
        data=_form(
            student,
            repeat="on",
            slots=_slots_json((0, "10:00", "11:00")),
            until_date="2026-11-09",
            interval_weeks="1",
        ),
        headers=HTMX,
    )

    assert response.status_code == 200
    assert "Дни отмечены как недоступные: Отпуск." in response.text
    assert "Затронуто занятий: 3." in response.text
    # Одно предупреждение на всю серию, уроки не созданы.
    assert response.text.count("form-banner--warning") == 1
    assert _lessons() == []


def test_create_series_with_ack_creates_all_lessons(
    owner, student, client, unavailability_factory
):
    """После подтверждения создаются все занятия серии."""
    unavailability_factory(
        tutor_id=owner,
        start_date=date(2026, 10, 19),
        end_date=date(2026, 10, 25),
    )

    response = client.post(
        "/tutor/lessons",
        data=_form(
            student,
            repeat="on",
            slots=_slots_json((0, "10:00", "11:00")),
            until_date="2026-11-09",
            interval_weeks="1",
            ack_unavailable="1",
        ),
        headers=HTMX,
    )

    assert response.text == ""
    assert len(_lessons()) == 4


def test_create_series_in_free_days_creates_immediately(
    owner, student, client, unavailability_factory
):
    """Серия, не задевающая отметки, создаётся сразу."""
    unavailability_factory(
        tutor_id=owner,
        start_date=date(2026, 11, 16),
        end_date=date(2026, 11, 20),
    )

    response = client.post(
        "/tutor/lessons",
        data=_form(
            student,
            repeat="on",
            slots=_slots_json((0, "10:00", "11:00")),
            until_date="2026-11-09",
            interval_weeks="1",
        ),
        headers=HTMX,
    )

    assert response.text == ""
    assert len(_lessons()) == 4


def test_ack_does_not_bypass_validation(
    owner, student, client, unavailability_factory
):
    """Флаг подтверждения не заменяет проверки формы: урок всё равно не создан."""
    _mark_monday(owner, unavailability_factory)

    response = client.post(
        "/tutor/lessons",
        data=_form(student, duration_min="13", ack_unavailable="1"),
        headers=HTMX,
    )

    assert "Выберите длительность урока из списка." in response.text
    assert _lessons() == []


# --------------------------------------------------------------------------
# 5.2 Баннер в разметке формы, отдельно от блока ошибок
# --------------------------------------------------------------------------


def test_warning_banner_is_separate_from_errors(
    owner, student, client, unavailability_factory
):
    """Баннер — свой блок, а не элемент `.error` (design.md D5, п. 3)."""
    _mark_monday(owner, unavailability_factory)

    page = client.post("/tutor/lessons", data=_form(student), headers=HTMX).text

    banner = re.search(
        r'<div class="form-banner form-banner--warning"[^>]*>.*?</div>', page, re.S
    )
    assert banner, "Баннера предупреждения нет в разметке"
    block = banner.group(0)
    assert 'role="alert"' in block
    assert "День отмечен как недоступный: Отпуск." in block
    # Скрытое поле подтверждения — внутри баннера.
    assert 'type="hidden" name="ack_unavailable" value="1"' in block
    # Блока ошибок нет: предупреждение — не ошибка валидации.
    assert '<div class="error" role="alert">' not in page


def test_no_banner_without_warning(owner, student, client):
    """Без отметки баннера нет."""
    page = client.get("/tutor/lessons/new").text
    assert "form-banner" not in page


@pytest.mark.parametrize(
    ("query", "has_hidden_field"),
    [
        ("&ack_unavailable=1", True),
        ("", False),
    ],
    ids=["ack-carried", "no-ack"],
)
def test_calendar_prefill_carries_ack_to_form(owner, client, query, has_hidden_field):
    """`?ack_unavailable=1` из календаря переносится в скрытое поле формы.

    Клиент уже спросил confirm() при клике по отмеченному дню — сервер не
    должен спрашивать второй раз, поэтому форма несёт подтверждение
    скрытым полем (design.md D5, п. 4). Один жест — одно подтверждение.
    Без подтверждения поля нет, и форму спросит баннер.
    """
    page = client.get(f"/tutor/lessons/new?starts_at=2026-10-19T10:00{query}").text

    assert 'value="2026-10-19T10:00"' in page
    if has_hidden_field:
        assert 'type="hidden" name="ack_unavailable" value="1"' in page
    else:
        assert 'name="ack_unavailable"' not in page


# --------------------------------------------------------------------------
# 5.3 Повторная отправка без флага снова предупреждает
# --------------------------------------------------------------------------


def test_repeat_submit_without_ack_warns_again(
    owner, student, client, unavailability_factory
):
    """Каждая отправка без подтверждения снова показывает предупреждение."""
    _mark_monday(owner, unavailability_factory)

    first = client.post("/tutor/lessons", data=_form(student), headers=HTMX)
    second = client.post("/tutor/lessons", data=_form(student), headers=HTMX)

    assert "День отмечен как недоступный" in first.text
    assert "День отмечен как недоступный" in second.text
    assert _lessons() == []


def test_next_lesson_in_same_day_warns_again(
    owner, student, client, unavailability_factory
):
    """После создания с подтверждением следующий урок в тот же день — снова с баннером."""
    _mark_monday(owner, unavailability_factory)

    created = client.post(
        "/tutor/lessons", data=_form(student, ack_unavailable="1"), headers=HTMX
    )
    assert created.headers["HX-Trigger"] == "lesson-saved"

    again = client.post(
        "/tutor/lessons",
        data=_form(student, starts_at="2026-10-19T12:00"),
        headers=HTMX,
    )
    assert "День отмечен как недоступный" in again.text
    assert len(_lessons()) == 1


# --------------------------------------------------------------------------
# 5.4 Правка даты урока
# --------------------------------------------------------------------------


def _insert_lesson(tutor_id: str, student_id: str, **overrides) -> str:
    """Урок напрямую в БД; возвращает id."""
    values = {
        "student_id": student_id,
        "type": "individual",
        "starts_at": datetime(2026, 10, 20, 10, 0),
        "duration_min": 60,
        "status": "planned",
    }
    values.update(overrides)
    with SessionLocal() as db:
        lesson = Lesson(**values)
        db.add(lesson)
        db.commit()
        return lesson.id


def test_update_start_to_marked_day_warns_and_keeps_lesson(
    owner, student, client, unavailability_factory
):
    """Смена «Начала» на отмеченный день без подтверждения: урок не изменён."""
    lesson_id = _insert_lesson(owner, student)
    _mark_monday(owner, unavailability_factory)

    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data=_form(student, starts_at="2026-10-19T10:00"),
        headers=HTMX,
    )

    assert "День отмечен как недоступный" in response.text
    (lesson,) = _lessons()
    assert lesson.starts_at == datetime(2026, 10, 20, 10, 0)


def test_update_start_to_marked_day_with_ack_changes_only_start(
    owner, student, client, unavailability_factory
):
    """С подтверждением урок сохранён с новым началом, прочие поля те же."""
    lesson_id = _insert_lesson(owner, student, note="Не трогать")
    _mark_monday(owner, unavailability_factory)

    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data=_form(
            student, starts_at="2026-10-19T10:00", note="Не трогать",
            ack_unavailable="1",
        ),
        headers=HTMX,
    )

    assert response.headers["HX-Trigger"] == "lesson-saved"
    (lesson,) = _lessons()
    assert lesson.starts_at == datetime(2026, 10, 19, 10, 0)
    assert lesson.note == "Не трогать"


def test_update_other_fields_in_marked_day_does_not_warn(
    owner, student, client, unavailability_factory
):
    """Правка прочих полей урока в отмеченном дне не предупреждает.

    Отметка уже стоит, урок в ней уже есть — предупреждение на каждое
    сохранение было бы шумом (design.md D5).
    """
    lesson_id = _insert_lesson(owner, student, starts_at=datetime(2026, 10, 19, 10, 0))
    _mark_monday(owner, unavailability_factory)

    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data=_form(
            student, starts_at="2026-10-19T10:00", note="Новая заметка",
        ),
        headers=HTMX,
    )

    assert response.headers["HX-Trigger"] == "lesson-saved"
    (lesson,) = _lessons()
    assert lesson.note == "Новая заметка"


# --------------------------------------------------------------------------
# 5.5 Перенос перетаскиванием
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("move_date", "ack", "status", "starts_at"),
    [
        # Отмеченный день без подтверждения: перенос отклонён, время прежнее.
        ("2026-10-19", None, 409, datetime(2026, 10, 20, 10, 0)),
        # Отмеченный день с подтверждением.
        ("2026-10-19", "1", 200, datetime(2026, 10, 19, 16, 30)),
        # Свободный день: подтверждение не запрашивается.
        ("2026-10-21", None, 200, datetime(2026, 10, 21, 16, 30)),
    ],
    ids=["marked-no-ack", "marked-with-ack", "free-day"],
)
def test_move_lesson_respects_unavailability_ack(
    owner, student, client, unavailability_factory, move_date, ack, status, starts_at
):
    """Перенос в отмеченный день требует подтверждения, в свободный — нет.

    Без подтверждения сервер отвечает 409 с причиной в теле, а время урока
    остаётся прежним; с подтверждением или в свободный день перенос
    сохраняется обычным порядком.
    """
    lesson_id = _insert_lesson(owner, student)
    _mark_monday(owner, unavailability_factory)

    data = {"date": move_date, "time": "16:30"}
    if ack:
        data["ack_unavailable"] = ack
    response = client.post(
        f"/tutor/lessons/{lesson_id}/move", data=data, headers=HTMX
    )

    assert response.status_code == status
    if status == 409:
        assert "День отмечен как недоступный: Отпуск." in response.json()["detail"]
    else:
        assert response.headers["HX-Trigger"] == "lesson-saved"
    (lesson,) = _lessons()
    assert lesson.starts_at == starts_at


# --------------------------------------------------------------------------
# 5.6 Клиент: confirm() на отмеченном дне, ack в запросах, без vacationForm
# --------------------------------------------------------------------------


def test_calendar_day_carries_reason_for_confirm(
    owner, client, unavailability_factory
):
    """Причина отметки приходит в `data-unavailable` — JS математику не считает."""
    unavailability_factory(
        tutor_id=owner,
        start_date=date(2026, 10, 19),
        end_date=date(2026, 10, 19),
        reason="sick",
    )
    text = client.get("/tutor/calendar?start=2026-10-19").text
    assert 'data-unavailable="Больничный"' in text
