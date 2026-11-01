"""Тесты недельного календаря кабинета ученика (change student-lessons-calendar).

Две группы проверок:

* сервис `cabinet/services/calendar.py` — окно недели в зоне репетитора,
  отсутствие чужих уроков, наличие прошедших уроков (они нужны серыми),
  карта ДЗ одним запросом и скрытие статуса «Не задано»;
* страница `/student` — календарь строго для чтения: нет `calendar.js`,
  нет адресов форм репетитора, нет данных для drag; листание недель
  работает ссылками `?start=…`, а HTMX-фрагмент не тащит каркас страницы.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event

from app.cabinet.services.calendar import (
    LESSON_LABEL,
    homework_by_lesson,
    student_calendar_context,
    student_week_lessons,
)
from app.cabinet.services.sessions import create_session
from app.database import SessionLocal, engine
from app.homework.models.homework import Homework
from app.student.models.student import Student
from app.tutor.models.tutor import Tutor

HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(tutor_factory):
    """Репетитор задачи: его зона (UTC) задаёт границы недели."""
    return tutor_factory(timezone="UTC")


def _login(client, student_id: str) -> None:
    with SessionLocal() as db:
        token = create_session(db, student_id)
    client.cookies.set("student_session", token)


def _make_homework(lesson_id: str, status: str) -> None:
    with SessionLocal() as db:
        db.add(
            Homework(
                lesson_id=lesson_id,
                assignment="Упражнение №3",
                status=status,
            )
        )
        db.commit()


def _context(student_id: str, tutor_id: str, monday: date) -> dict:
    with SessionLocal() as db:
        student = db.get(Student, student_id)
        tutor = db.get(Tutor, tutor_id)
        return student_calendar_context(db, student, tutor, monday)


def _events(context: dict) -> list[dict]:
    return [event for day in context["days"] for event in day["lessons"]]


# --------------------------------------------------------------------------
# Сервис: выборка недели
# --------------------------------------------------------------------------


def test_week_lessons_only_own_lessons(owner, student_factory, lesson_factory):
    """В неделю ученика попадают только его уроки, чужие не видны."""
    mine = student_factory(tutor_id=owner, first_name="Аня")
    other = student_factory(tutor_id=owner, first_name="Борис")
    own_id = lesson_factory(
        student_id=mine,
        status="planned",
        starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )
    lesson_factory(
        student_id=other,
        status="planned",
        starts_at=datetime(2027, 3, 1, 11, 0, tzinfo=UTC),
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, owner)
        rows = student_week_lessons(db, mine, date(2027, 3, 1), tutor)

    assert [row.lesson.id for row in rows] == [own_id]


def test_week_lessons_include_past_and_completed(
    owner, student_factory, lesson_factory
):
    """Прошедшие и проведённые уроки остаются в неделе — они показываются серыми."""
    student_id = student_factory(tutor_id=owner)
    planned_past = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 3, 2, 10, 0, tzinfo=UTC),
    )
    completed = lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=datetime(2027, 3, 3, 10, 0, tzinfo=UTC),
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, owner)
        rows = student_week_lessons(db, student_id, date(2027, 3, 1), tutor)

    assert [row.lesson.id for row in rows] == [planned_past, completed]


def test_week_lessons_use_tutor_week_bounds(owner, student_factory, lesson_factory):
    """Окно недели — [пн 00:00, следующий пн 00:00): вс 23:00 входит, пн 00:00 — нет."""
    student_id = student_factory(tutor_id=owner)
    sunday = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 3, 7, 23, 0, tzinfo=UTC),
    )
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 3, 8, 0, 0, tzinfo=UTC),
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, owner)
        rows = student_week_lessons(db, student_id, date(2027, 3, 1), tutor)

    assert [row.lesson.id for row in rows] == [sunday]


def test_group_lesson_uses_group_name(
    owner, student_factory, lesson_factory, group_factory, group_member_factory
):
    """Групповой урок подписан названием группы, индивидуальный — «Урок»."""
    student_id = student_factory(tutor_id=owner)
    group_id = group_factory(tutor_id=owner, name="Английский B2")
    group_member_factory(group_id=group_id, student_id=student_id)
    lesson_factory(
        group_id=group_id,
        status="planned",
        starts_at=datetime(2027, 3, 1, 15, 0, tzinfo=UTC),
    )
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )

    context = _context(student_id, owner, date(2027, 3, 1))
    names = [event["target_name"] for event in _events(context)]

    assert "Английский B2" in names
    assert LESSON_LABEL in names


# --------------------------------------------------------------------------
# Сервис: домашние задания
# --------------------------------------------------------------------------


def test_homework_map_hides_not_assigned(owner, student_factory, lesson_factory):
    """«Не задано» — отсутствие ДЗ: в карту статусов не попадает."""
    student_id = student_factory(tutor_id=owner)
    assigned = lesson_factory(student_id=student_id, status="completed")
    empty = lesson_factory(student_id=student_id, status="completed")
    _make_homework(assigned, "assigned")
    _make_homework(empty, "not_assigned")

    with SessionLocal() as db:
        statuses = homework_by_lesson(db, [assigned, empty])

    assert statuses == {assigned: "assigned"}


def test_homework_map_is_single_query(owner, student_factory, lesson_factory):
    """Число запросов не растёт с числом уроков недели (нет N+1)."""
    student_id = student_factory(tutor_id=owner)
    one = lesson_factory(student_id=student_id, status="completed")
    _make_homework(one, "assigned")

    many = [
        lesson_factory(student_id=student_id, status="completed")
        for _ in range(6)
    ]
    for lesson_id in many:
        _make_homework(lesson_id, "submitted")

    def _count(lesson_ids: list[str]) -> int:
        counter = {"count": 0}

        def _on_execute(*args, **kwargs):
            counter["count"] += 1

        with SessionLocal() as db:
            event.listen(engine, "before_cursor_execute", _on_execute)
            try:
                homework_by_lesson(db, lesson_ids)
            finally:
                event.remove(engine, "before_cursor_execute", _on_execute)
        return counter["count"]

    assert _count(many) == _count([one])


def test_context_marks_homework_status_and_label(
    owner, student_factory, lesson_factory
):
    """В представлении карточки есть статус и подпись ДЗ; без ДЗ — пусто."""
    student_id = student_factory(tutor_id=owner)
    with_homework = lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )
    without_homework = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 3, 1, 12, 0, tzinfo=UTC),
    )
    _make_homework(with_homework, "checked")

    events = {event["lesson_id"]: event for event in _events(
        _context(student_id, owner, date(2027, 3, 1))
    )}

    assert events[with_homework]["homework_status"] == "checked"
    assert events[with_homework]["homework_label"] == "Проверено"
    assert events[without_homework]["homework_status"] == ""
    assert events[without_homework]["homework_label"] == ""


def test_context_marks_past_lessons(owner, student_factory, lesson_factory):
    """Прошедший урок серый, будущий — цветом цели."""
    student_id = student_factory(tutor_id=owner)
    past = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2020, 1, 1, 10, 0, tzinfo=UTC),
    )
    future = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2099, 1, 1, 10, 0, tzinfo=UTC),
    )

    events = {event["lesson_id"]: event for event in _events(
        _context(student_id, owner, date(2020, 1, 1))
    )}
    future_events = {
        event["lesson_id"]: event
        for event in _events(_context(student_id, owner, date(2099, 1, 1)))
    }

    assert events[past]["is_past"] is True
    assert events[past]["color"] == "var(--muted-foreground)"
    assert future_events[future]["is_past"] is False


def test_context_does_not_show_price_or_unavailability(
    owner, student_factory, lesson_factory
):
    """Цена урока и отметки недоступности репетитора ученику не показываются."""
    student_id = student_factory(tutor_id=owner)
    lesson_factory(
        student_id=student_id,
        price=1200,
        status="planned",
        starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )

    context = _context(student_id, owner, date(2027, 3, 1))
    event = _events(context)[0]

    assert event["price_label"] == ""
    assert all(day["unavailable"] == "" for day in context["days"])


# --------------------------------------------------------------------------
# Страница: только чтение
# --------------------------------------------------------------------------


def test_calendar_page_is_read_only(client, owner, student_factory, lesson_factory):
    """Календарь нельзя редактировать: нет скрипта, форм и данных для drag."""
    student_id = student_factory(tutor_id=owner)
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )
    _login(client, student_id)

    page = client.get("/student?start=2027-03-01").text

    # Сетка недели отрисована.
    assert 'id="student-calendar"' in page
    assert 'class="cal-grid"' in page
    assert "10:00 – 11:00" in page
    # Ни скрипта календаря репетитора, ни его адресов и обработчиков.
    assert "/static/calendar.js" not in page
    assert 'hx-get="/tutor/' not in page
    assert '@click="openSlot' not in page
    assert "data-start-min" not in page
    assert "data-duration-min" not in page
    # Карточка не обещает перетаскивание.
    assert "cal-event--readonly" in page


def test_calendar_page_has_week_navigation(
    client, owner, student_factory, lesson_factory
):
    """Листание недель: ссылки `?start=` и «Сегодня» без параметра."""
    student_id = student_factory(tutor_id=owner)
    _login(client, student_id)

    page = client.get("/student?start=2027-03-01").text

    assert "?start=2027-02-22" in page
    assert "?start=2027-03-08" in page
    assert 'hx-target="#student-calendar"' in page
    assert "1 марта – 7 марта 2027" in page
    # Бейдж часового пояса: время показано в зоне репетитора.
    assert "cal-tz" in page
    assert "UTC" in page


def test_calendar_htmx_fragment_has_no_shell(client, owner, student_factory):
    """HTMX-фрагмент — только область календаря, без каркаса страницы."""
    student_id = student_factory(tutor_id=owner)
    _login(client, student_id)

    fragment = client.get("/student?start=2027-03-01", headers=HTMX).text

    assert 'id="student-calendar"' in fragment
    assert "<html" not in fragment
    assert "sidebar" not in fragment
    assert "Кабинет ученика" not in fragment
    # Карточка ближайшего занятия — часть страницы, а не области календаря:
    # листание недель её не перерисовывает.
    assert "Ближайшее занятие" not in fragment


def test_calendar_shows_homework_badge_by_status(
    client, owner, student_factory, lesson_factory
):
    """Значок ДЗ: класс зависит от статуса, подпись — в title и aria-label."""
    student_id = student_factory(tutor_id=owner)
    assigned = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )
    checked = lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=datetime(2027, 3, 2, 10, 0, tzinfo=UTC),
    )
    _make_homework(assigned, "assigned")
    _make_homework(checked, "checked")
    _login(client, student_id)

    page = client.get("/student?start=2027-03-01").text

    assert "cal-hw-badge--assigned" in page
    assert "cal-hw-badge--checked" in page
    assert "Домашнее задание: Задано" in page
    assert "Домашнее задание: Проверено" in page


def test_calendar_hides_badge_for_not_assigned(
    client, owner, student_factory, lesson_factory
):
    """Без ДЗ (статус «Не задано») значка в карточке нет."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )
    _make_homework(lesson_id, "not_assigned")
    _login(client, student_id)

    page = client.get("/student?start=2027-03-01").text

    assert "cal-hw-badge" not in page
    assert "Не задано" not in page


def test_calendar_bad_week_falls_back_to_current(
    client, owner, student_factory
):
    """Кривой `?start=` — не ошибка, а текущая неделя."""
    student_id = student_factory(tutor_id=owner)
    _login(client, student_id)

    response = client.get("/student?start=не-дата")

    assert response.status_code == 200
    assert 'id="student-calendar"' in response.text


def test_calendar_week_outside_limits_is_empty(
    client, owner, student_factory, lesson_factory
):
    """Урок другой недели в текущую не попадает."""
    student_id = student_factory(tutor_id=owner)
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )
    _login(client, student_id)

    page = client.get("/student?start=2027-03-01").text
    next_week = client.get(
        "/student?start=" + (date(2027, 3, 1) + timedelta(days=7)).isoformat()
    ).text

    assert "10:00 – 11:00" in page
    assert "10:00 – 11:00" not in next_week
    assert "На этой неделе уроков нет" in next_week
