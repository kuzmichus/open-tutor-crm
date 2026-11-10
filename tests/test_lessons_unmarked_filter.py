"""Фильтр «Не отмеченные» в списке уроков (страница и htmx-партиал).

Через HTTP, как у пользователя: `?status=unmarked` на `/tutor/lessons` и
`/tutor/lessons/list` показывает только прошедшие уроки, оставшиеся в
«Запланирован»; комбинируется с поиском; неизвестное значение трактуется
как «Все статусы».
"""

from datetime import timedelta

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.tutor.services.clock import utcnow

PASSWORD = "Секретный-Пароль-1"


def _login(client, tutor_factory, email: str) -> str:
    tutor_id = tutor_factory(email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _lesson_row(lesson_id: str) -> str:
    """Атрибут строки таблицы, по которому ищем урок в разметке."""
    return f'lesson-row-{lesson_id}'


def test_shows_only_unmarked(client, tutor_factory, student_factory, lesson_factory):
    """Прошедший «Запланирован» виден; будущий и проведённый — нет."""
    tutor_id = _login(client, tutor_factory, "unmarked-filter@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    unmarked = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() - timedelta(hours=1),
    )
    future = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() + timedelta(days=1),
    )
    done = lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=utcnow() - timedelta(days=2),
    )

    for url in ("/tutor/lessons?status=unmarked", "/tutor/lessons/list?status=unmarked"):
        html = client.get(url).text
        assert _lesson_row(unmarked) in html, url
        assert _lesson_row(future) not in html, url
        assert _lesson_row(done) not in html, url


def test_default_shows_all(client, tutor_factory, student_factory, lesson_factory):
    """Без фильтра — все статусы, включая будущий и проведённый."""
    tutor_id = _login(client, tutor_factory, "unmarked-all@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=utcnow() - timedelta(hours=1))
    lesson_factory(student_id=student_id, status="planned", starts_at=utcnow() + timedelta(days=1))
    lesson_factory(student_id=student_id, status="completed", starts_at=utcnow() - timedelta(days=2))

    html = client.get("/tutor/lessons").text
    assert html.count("lessons-table__row") == 3


def test_unknown_status_means_all(client, tutor_factory, student_factory, lesson_factory):
    """Неизвестное значение фильтра не сужает список."""
    tutor_id = _login(client, tutor_factory, "unmarked-bogus@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=utcnow() - timedelta(hours=1))
    lesson_factory(student_id=student_id, status="completed", starts_at=utcnow() - timedelta(days=2))

    html = client.get("/tutor/lessons?status=bogus").text
    assert html.count("lessons-table__row") == 2


def test_combined_with_search(client, tutor_factory, student_factory, lesson_factory):
    """Фильтр статуса комбинируется с поиском по имени ученика."""
    tutor_id = _login(client, tutor_factory, "unmarked-search@example.com")
    match = student_factory(tutor_id=tutor_id, first_name="Анна")
    other = student_factory(tutor_id=tutor_id, first_name="Борис")
    lesson_factory(
        student_id=match,
        status="planned",
        starts_at=utcnow() - timedelta(hours=1),
    )
    lesson_factory(
        student_id=other,
        status="planned",
        starts_at=utcnow() - timedelta(hours=2),
    )

    html = client.get("/tutor/lessons/list?status=unmarked&q=анна").text
    assert html.count("lessons-table__row") == 1
    assert "Анна" in html
    assert "Борис" not in html


def test_select_on_page(client, tutor_factory):
    """На странице есть селект статуса; выбранное значение сохраняется."""
    _login(client, tutor_factory, "unmarked-select@example.com")

    page = client.get("/tutor/lessons").text
    assert '<option value="unmarked"' in page
    assert "Не отмеченные" in page
    assert "Все статусы" in page

    selected = client.get("/tutor/lessons?status=unmarked").text
    assert '<option value="unmarked" selected>' in selected


def test_empty_filter_state(client, tutor_factory, student_factory, lesson_factory):
    """Пустой результат с активным фильтром — пояснение, а не пустота."""
    tutor_id = _login(client, tutor_factory, "unmarked-empty@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=utcnow() - timedelta(days=2),
    )

    html = client.get("/tutor/lessons/list?status=unmarked").text
    assert "Ничего не найдено" in html
    assert "Измените поисковый запрос или фильтры." in html


def test_isolation(client, tutor_factory, student_factory, lesson_factory):
    """Фильтр показывает только уроки вошедшего репетитора."""
    other_tutor = tutor_factory(email="unmarked-other@example.com")
    other_student = student_factory(tutor_id=other_tutor)
    other_lesson = lesson_factory(
        student_id=other_student,
        status="planned",
        starts_at=utcnow() - timedelta(hours=1),
    )

    _login(client, tutor_factory, "unmarked-mine@example.com")
    html = client.get("/tutor/lessons?status=unmarked").text
    assert _lesson_row(other_lesson) not in html
