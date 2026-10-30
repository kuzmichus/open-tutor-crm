"""Тесты вкладки «Домашние задания» кабинета: список, отправка ответа,
повторная отправка, закрытие после проверки и изоляция по ученику
(change cabinet-homework)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.cabinet.services.sessions import create_session
from app.database import SessionLocal
from app.homework.models.answer import HomeworkAnswer
from app.homework.models.answer_link import HomeworkAnswerLink
from app.homework.models.homework import Homework

PASSWORD = "Пароль-1"
HTMX = {"HX-Request": "true"}
ASSIGNMENT = "Дома нужно сделать упражнение №3"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="cabinet-hw@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "cabinet-hw@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _student_login(client, student_id: str) -> None:
    """Выдаёт ученику сессию кабинета в текущем клиенте."""
    with SessionLocal() as db:
        token = create_session(db, student_id)
    client.cookies.set("student_session", token)


def _make_homework(
    lesson_id: str,
    *,
    assignment: str = ASSIGNMENT,
    status: str = "assigned",
    due_at: datetime | None = None,
    teacher_comment: str | None = None,
    recording_url: str | None = None,
) -> str:
    """Запись ДЗ урока; возвращает её id."""
    with SessionLocal() as db:
        homework = Homework(
            lesson_id=lesson_id,
            assignment=assignment,
            status=status,
            due_at=due_at,
            teacher_comment=teacher_comment,
            recording_url=recording_url,
        )
        db.add(homework)
        db.commit()
        return str(homework.id)


def _get_answer(homework_id: str) -> HomeworkAnswer | None:
    with SessionLocal() as db:
        return db.scalars(
            select(HomeworkAnswer).where(HomeworkAnswer.homework_id == homework_id)
        ).one_or_none()


# --------------------------------------------------------------------------
# Страница «Домашние задания»: список карточек
# --------------------------------------------------------------------------


def test_homework_page_requires_session(client):
    """Без сессии ученика страница недоступна — редирект на вход."""
    response = client.get("/student/homework", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/student/login"


def test_homework_page_lists_assigned(client, owner, student_factory, lesson_factory):
    """Карточка заданного ДЗ: заголовок урока, чип, срок, задание, ссылка меню."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=datetime(2026, 10, 30, 10, 0, tzinfo=UTC),
    )
    homework_id = _make_homework(
        lesson_id,
        due_at=datetime(2026, 10, 30, 12, 0, tzinfo=UTC),
        teacher_comment="Постарайся оформить аккуратно",
        recording_url="https://disk.yandex.ru/recording",
    )
    _student_login(client, student_id)

    page = client.get("/student/homework").text

    assert "Домашние задания" in page
    assert "урок 30 октября 2026" in page
    assert "Задано" in page
    assert "Срок: 30 октября 2026, 12:00" in page
    assert ASSIGNMENT in page
    assert "Постарайся оформить аккуратно" in page
    assert "https://disk.yandex.ru/recording" in page
    # Форма ответа на месте; карточка свёрнута (нет open у этой карточки).
    assert 'name="text"' in page
    assert f'id="hw-card-{homework_id}" open' not in page
    # Пункт меню — ссылка с активным состоянием.
    assert 'href="/student/homework"' in page
    assert "nav-item--active" in page


def test_not_assigned_homework_hidden(client, owner, student_factory, lesson_factory):
    """ДЗ со статусом «Не задано» — пустая запись: в кабинете её нет."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(student_id=student_id)
    _make_homework(lesson_id, assignment="Скрытое задание", status="not_assigned")
    _student_login(client, student_id)

    page = client.get("/student/homework").text
    assert "Скрытое задание" not in page
    assert "Домашних заданий пока нет" in page


def test_homework_sorted_newest_first(client, owner, student_factory, lesson_factory):
    """Свежее задание сверху: сортировка по дате урока по убыванию."""
    student_id = student_factory(tutor_id=owner)
    older = lesson_factory(
        student_id=student_id, starts_at=datetime(2026, 10, 20, 10, 0, tzinfo=UTC)
    )
    newer = lesson_factory(
        student_id=student_id, starts_at=datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
    )
    _make_homework(older, assignment="Старое задание")
    _make_homework(newer, assignment="Свежее задание")
    _student_login(client, student_id)

    page = client.get("/student/homework").text
    assert page.index("Свежее задание") < page.index("Старое задание")


def test_group_homework_visible_and_isolated(
    client, owner, student_factory, lesson_factory, group_factory, group_member_factory
):
    """Групповое ДЗ видно участнику группы и скрыто от другого ученика."""
    student_a = student_factory(tutor_id=owner, first_name="Аня")
    student_b = student_factory(tutor_id=owner, first_name="Борис")
    group_id = group_factory()
    group_member_factory(group_id=group_id, student_id=student_a)
    group_lesson = lesson_factory(
        group_id=group_id, starts_at=datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
    )
    _make_homework(group_lesson, assignment="Групповое задание")

    b_lesson = lesson_factory(
        student_id=student_b, starts_at=datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
    )
    _make_homework(b_lesson, assignment="Задание Бориса")

    _student_login(client, student_a)
    page = client.get("/student/homework").text
    assert "Групповое задание" in page
    assert "Задание Бориса" not in page

    _student_login(client, student_b)
    page = client.get("/student/homework").text
    assert "Групповое задание" not in page
    assert "Задание Бориса" in page


# --------------------------------------------------------------------------
# Отправка ответа
# --------------------------------------------------------------------------


def test_submit_answer_htmx(client, owner, student_factory, lesson_factory):
    """Отправка ответа: запись и ссылки созданы, ДЗ стало «Сдано»."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(student_id=student_id)
    homework_id = _make_homework(lesson_id)
    _student_login(client, student_id)

    response = client.post(
        f"/student/homework/{homework_id}/answer",
        data={"text": "Упражнение сделано", "links": ["https://disk.yandex.ru/a", "https://cloud.mail.ru/b"]},
        headers=HTMX,
    )
    assert response.status_code == 200
    assert "Сдано" in response.text
    assert "Ответ отправлен репетитору" in response.text
    # Карточка после отправки остаётся раскрытой.
    assert f'id="hw-card-{homework_id}" open' in response.text

    with SessionLocal() as db:
        answer = _get_answer(homework_id)
        assert answer is not None and answer.text == "Упражнение сделано"
        links = db.scalars(
            select(HomeworkAnswerLink)
            .where(HomeworkAnswerLink.answer_id == answer.id)
            .order_by(HomeworkAnswerLink.position)
        ).all()
        assert [link.url for link in links] == [
            "https://disk.yandex.ru/a",
            "https://cloud.mail.ru/b",
        ]
        homework = db.get(Homework, homework_id)
        assert homework.status == "submitted"


def test_submit_answer_without_js_redirects(client, owner, student_factory, lesson_factory):
    """Форма работает без JS: POST отвечает 303 на страницу списка."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(student_id=student_id)
    homework_id = _make_homework(lesson_id)
    _student_login(client, student_id)

    response = client.post(
        f"/student/homework/{homework_id}/answer",
        data={"text": "Готово"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/student/homework"
    assert _get_answer(homework_id) is not None


def test_submit_answer_rejects_empty(client, owner, student_factory, lesson_factory):
    """Пустой ответ отклонён: ни текста, ни ссылок — ошибка, записи нет."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(student_id=student_id)
    homework_id = _make_homework(lesson_id)
    _student_login(client, student_id)

    page = client.post(
        f"/student/homework/{homework_id}/answer",
        data={"text": "", "links": [""]},
        headers=HTMX,
    ).text
    assert "Напишите ответ или добавьте ссылку" in page
    assert _get_answer(homework_id) is None


def test_submit_answer_rejects_bad_link_keeps_input(
    client, owner, student_factory, lesson_factory
):
    """Кривая ссылка отклонена, введённый текст вернулся в форму."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(student_id=student_id)
    homework_id = _make_homework(lesson_id)
    _student_login(client, student_id)

    page = client.post(
        f"/student/homework/{homework_id}/answer",
        data={"text": "Мой ответ", "links": ["ftp://example.com/file"]},
        headers=HTMX,
    ).text
    assert "Каждая ссылка должна начинаться" in page
    assert "Мой ответ" in page
    assert _get_answer(homework_id) is None


def test_resubmit_replaces_links(client, owner, student_factory, lesson_factory):
    """Повторная отправка обновляет ответ и заменяет ссылки целиком."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(student_id=student_id)
    homework_id = _make_homework(lesson_id)
    _student_login(client, student_id)

    client.post(
        f"/student/homework/{homework_id}/answer",
        data={"text": "Первая версия", "links": ["https://disk.yandex.ru/old"]},
        headers=HTMX,
    )
    client.post(
        f"/student/homework/{homework_id}/answer",
        data={"text": "Исправленная версия", "links": ["https://cloud.mail.ru/new"]},
        headers=HTMX,
    )

    with SessionLocal() as db:
        answers = db.scalars(
            select(HomeworkAnswer).where(HomeworkAnswer.homework_id == homework_id)
        ).all()
        assert len(answers) == 1
        links = db.scalars(
            select(HomeworkAnswerLink)
            .where(HomeworkAnswerLink.answer_id == answers[0].id)
            .order_by(HomeworkAnswerLink.position)
        ).all()
        assert answers[0].text == "Исправленная версия"
        assert [link.url for link in links] == ["https://cloud.mail.ru/new"]


def test_saved_answer_prefills_form(client, owner, student_factory, lesson_factory):
    """Повторное открытие карточки показывает отправленный ответ."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(student_id=student_id)
    homework_id = _make_homework(lesson_id)
    _student_login(client, student_id)

    client.post(
        f"/student/homework/{homework_id}/answer",
        data={"text": "Упражнение сделано"},
        headers=HTMX,
    )
    page = client.get("/student/homework").text
    assert "Упражнение сделано" in page
    assert "Сдано" in page


# --------------------------------------------------------------------------
# Проверенное ДЗ закрыто для ответа
# --------------------------------------------------------------------------


def test_checked_homework_is_read_only(client, owner, student_factory, lesson_factory):
    """ДЗ «Проверено»: форма не показывается, POST отклонён с сообщением."""
    student_id = student_factory(tutor_id=owner)
    lesson_id = lesson_factory(student_id=student_id)
    homework_id = _make_homework(
        lesson_id, status="checked", teacher_comment="Молодец!"
    )
    _student_login(client, student_id)

    page = client.get("/student/homework").text
    assert "Проверено" in page
    assert "Ответ ученика" in page
    assert 'name="text"' not in page

    response = client.post(
        f"/student/homework/{homework_id}/answer",
        data={"text": "Попытка перезаписать"},
        headers=HTMX,
    )
    assert "Задание уже проверено репетитором" in response.text
    assert _get_answer(homework_id) is None
    with SessionLocal() as db:
        assert db.get(Homework, homework_id).status == "checked"


# --------------------------------------------------------------------------
# Изоляция и доступ
# --------------------------------------------------------------------------


def test_answer_to_foreign_homework_404(
    client, owner, student_factory, lesson_factory
):
    """Чужое ДЗ неотличимо от несуществующего: 404, ответ не сохранён."""
    student_a = student_factory(tutor_id=owner, first_name="Аня")
    student_b = student_factory(tutor_id=owner, first_name="Борис")
    b_lesson = lesson_factory(student_id=student_b)
    foreign_homework = _make_homework(b_lesson, assignment="Чужое задание")

    _student_login(client, student_a)
    response = client.post(
        f"/student/homework/{foreign_homework}/answer",
        data={"text": "Не моё"},
        headers=HTMX,
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert _get_answer(foreign_homework) is None
