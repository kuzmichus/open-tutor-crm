"""Баннер-напоминание о не отмеченных уроках (партиал `/tutor/notices`).

Поведение проверяется через HTTP тем же путём, что у пользователя:
контейнер на страницах кабинета запрашивает партиал, разметка ищется по
тексту и атрибутам. Время уроков строится от «сейчас» (фабрика даёт зону
UTC): баннер живёт окном «закончился, но ещё не отмечен».
"""

from datetime import UTC, datetime, timedelta

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.tutor.services.clock import utcnow

PASSWORD = "Секретный-Пароль-1"


def _login(client, tutor_factory, email: str, name: str = "Репетитор") -> str:
    """Создаёт репетитора и входит под ним; возвращает id."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _insert_lesson(tutor_id: str, student_id: str, **overrides) -> str:
    """Урок напрямую в БД (страницы, а не форма); возвращает id."""
    values = {
        "student_id": student_id,
        "type": "individual",
        "starts_at": utcnow() - timedelta(hours=1),
        "duration_min": 60,
        "price": 1200,
        "status": "planned",
    }
    values.update(overrides)
    with SessionLocal() as db:
        lesson = Lesson(**values)
        db.add(lesson)
        db.commit()
        return lesson.id


def test_requires_session(client):
    """Без сессии партиал недоступен: редирект на вход."""
    response = client.get("/tutor/notices", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_shows_unmarked_lesson(client, tutor_factory, student_factory, lesson_factory):
    """Прошедший «Запланирован» урок виден: подпись, имя, время, «Открыть»."""
    tutor_id = _login(client, tutor_factory, "notices-main@example.com")
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Иванов")
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() - timedelta(hours=1),
        duration_min=60,
    )

    response = client.get("/tutor/notices")
    assert response.status_code == 200
    html = response.text
    assert "1 урок не отмечен" in html
    assert "Иван Иванов" in html
    # «Открыть» ведёт в фильтр списка (design D6 change'а unmarked-lessons).
    assert 'href="/tutor/lessons?status=unmarked"' in html
    assert 'aria-label="Скрыть напоминание"' in html
    # Ключ-состояние для клиентского закрытия — id урока.
    assert f"noticeBanner('{lesson_id}')" in html


def test_future_planned_not_shown(client, tutor_factory, student_factory, lesson_factory):
    """Будущий урок — не напоминание: партиал отвечает пустым телом."""
    tutor_id = _login(client, tutor_factory, "notices-future@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() + timedelta(days=1),
    )

    response = client.get("/tutor/notices")
    assert response.status_code == 200
    assert response.text == ""


def test_completed_not_shown(client, tutor_factory, student_factory, lesson_factory):
    """Проведённый урок в баннер не попадает, даже если давно в прошлом."""
    tutor_id = _login(client, tutor_factory, "notices-done@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=utcnow() - timedelta(days=3),
    )

    response = client.get("/tutor/notices")
    assert response.text == ""


def test_plural_form_for_two(client, tutor_factory, student_factory, lesson_factory):
    """Русская плюрализация: «2 урока не отмечены»."""
    tutor_id = _login(client, tutor_factory, "notices-two@example.com")
    for _ in range(2):
        student_id = student_factory(tutor_id=tutor_id)
        lesson_factory(
            student_id=student_id,
            status="planned",
            starts_at=utcnow() - timedelta(hours=2),
        )

    html = client.get("/tutor/notices").text
    assert "2 урока не отмечены" in html


def test_shows_latest_lesson_first(client, tutor_factory, student_factory, lesson_factory):
    """Из нескольких не отмеченных в баннере — самый свежий урок."""
    tutor_id = _login(client, tutor_factory, "notices-latest@example.com")
    old_student = student_factory(tutor_id=tutor_id, first_name="Старый")
    new_student = student_factory(tutor_id=tutor_id, first_name="Свежий")
    lesson_factory(
        student_id=old_student,
        status="planned",
        starts_at=utcnow() - timedelta(days=2),
    )
    lesson_factory(
        student_id=new_student,
        status="planned",
        starts_at=utcnow() - timedelta(hours=1),
        duration_min=60,
    )

    html = client.get("/tutor/notices").text
    assert "3 урока не отмечены" not in html
    assert "2 урока не отмечены" in html
    assert "Свежий" in html
    assert "Старый" not in html


def test_isolation(client, tutor_factory, student_factory, lesson_factory):
    """В баннере только уроки вошедшего репетитора."""
    other_tutor = tutor_factory(email="notices-other@example.com")
    other_student = student_factory(tutor_id=other_tutor, first_name="Чужой")
    lesson_factory(
        student_id=other_student,
        status="planned",
        starts_at=utcnow() - timedelta(hours=1),
    )

    _login(client, tutor_factory, "notices-mine@example.com")
    assert client.get("/tutor/notices").text == ""


def test_explanation_only_with_flag(client, tutor_factory, student_factory, lesson_factory):
    """Пояснение про автозавершение приходит только с `?explain=1`."""
    tutor_id = _login(client, tutor_factory, "notices-explain@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() - timedelta(hours=1),
    )

    hint = "через 24 часа он будет завершён автоматически"
    assert hint in client.get("/tutor/notices?explain=1").text
    assert hint not in client.get("/tutor/notices").text


def test_group_lesson_shows_group_name(
    client, tutor_factory, student_factory, group_factory, lesson_factory
):
    """Групповой урок в баннере подписан именем группы."""
    tutor_id = _login(client, tutor_factory, "notices-group@example.com")
    group_id = group_factory(tutor_id=tutor_id, name="Математика 7Б")
    lesson_factory(
        student_id=None,
        group_id=group_id,
        status="planned",
        starts_at=utcnow() - timedelta(hours=1),
    )

    html = client.get("/tutor/notices").text
    assert "1 урок не отмечен" in html
    assert "Математика 7Б" in html


def _container(html: str, explain: bool = False) -> bool:
    """Есть ли контейнер баннера с ожидаемым адресом партиала."""
    expected = f'hx-get="/tutor/notices{"?explain=1" if explain else ""}"'
    return expected in html


def test_home_page_container_with_explanation(client, tutor_factory):
    """На главной контейнер запрашивает баннер с пояснением."""
    _login(client, tutor_factory, "notices-home@example.com")
    assert _container(client.get("/tutor/").text, explain=True)


def test_other_pages_container(client, tutor_factory, student_factory):
    """Остальные страницы кабинета несут контейнер без пояснения."""
    tutor_id = _login(client, tutor_factory, "notices-pages@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    for url in (
        "/tutor/students",
        "/tutor/lessons",
        "/tutor/calendar",
        "/tutor/groups",
        "/tutor/profile",
        f"/tutor/students/{student_id}",
    ):
        assert _container(client.get(url).text), url
