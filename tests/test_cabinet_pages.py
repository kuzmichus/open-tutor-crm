"""Тесты страниц кабинета: регистрация по приглашению, вход, «Мои уроки»,
выход; изоляция учеников и независимость сессий ученика и репетитора
(change student-cabinet-access).
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.database import SessionLocal
from app.cabinet.models.invite import StudentCabinetInvite
from app.cabinet.services.invites import create_invite
from app.cabinet.services.sessions import create_session
from app.lesson.models.lesson import Lesson
from app.student.models.student_access import StudentAccess
from app.tutor.services.password_hasher import PasswordHasher

PASSWORD = "Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="cabinet-owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "cabinet-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _make_invite(tutor_id: str, student_id: str, token: str = "page-test-token"):
    with SessionLocal() as db:
        create_invite(db, tutor_id, student_id)
        invite = db.query(StudentCabinetInvite).filter_by(student_id=student_id).one()
        invite.token = token
        db.commit()
        return invite.token


def _expire_invite(token: str) -> None:
    with SessionLocal() as db:
        invite = db.query(StudentCabinetInvite).filter_by(token=token).one()
        invite.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()


# --------------------------------------------------------------------------
# 5.1 Регистрация по приглашению
# --------------------------------------------------------------------------


def test_register_page_shows_only_email_and_password(client, owner, student_factory):
    """Публичная форма: Email и Пароль; имени ученика и согласий нет."""
    student_id = student_factory(
        tutor_id=owner, first_name="Секретное", last_name="Имя"
    )
    token = _make_invite(owner, student_id)

    page = client.get(f"/invite/{token}").text
    assert 'name="email"' in page
    assert 'name="password"' in page
    assert "Секретное" not in page
    assert "Имя" not in page
    assert "offer" not in page.lower() and "согласи" not in page.lower()
    # Публичность: без сессии репетитора и ученика.
    assert "student_session" not in page


def test_register_creates_access_and_session(client, owner, student_factory):
    """Успешная регистрация: вход привязан, ученик в кабинете (сессия)."""
    student_id = student_factory(tutor_id=owner)
    token = _make_invite(owner, student_id)

    response = client.post(
        f"/invite/{token}",
        data={"email": "masha@example.com", "password": "пароль-пароль"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/student"
    assert "student_session" in response.headers.get("set-cookie", "")

    with SessionLocal() as db:
        access = db.query(StudentAccess).filter_by(student_id=student_id).one()
        assert access.email == "masha@example.com"
        assert PasswordHasher().verify("пароль-пароль", access.password_hash)
        assert db.query(StudentCabinetInvite).filter_by(token=token).one().used_at

    # Редирект ведёт в кабинет без повторного входа.
    assert client.get("/student", follow_redirects=False).status_code == 200


def test_register_updates_manual_access(client, owner, student_factory):
    """Регистрация поверх ручного входа: email и пароль обновлены."""
    student_id = student_factory(tutor_id=owner)
    with SessionLocal() as db:
        db.add(
            StudentAccess(
                student_id=student_id,
                login="masha",
                password_hash=PasswordHasher().hash("старый-пароль"),
            )
        )
        db.commit()
    token = _make_invite(owner, student_id)

    response = client.post(
        f"/invite/{token}",
        data={"email": "masha@example.com", "password": "новый-пароль"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        rows = db.query(StudentAccess).filter_by(student_id=student_id).all()
        assert len(rows) == 1
        assert rows[0].login == "masha"
        assert rows[0].email == "masha@example.com"
        assert PasswordHasher().verify("новый-пароль", rows[0].password_hash)


def test_register_rejects_taken_email(client, owner, student_factory):
    """Занятый email: отклонён с сообщением, вход не создан."""
    student_id = student_factory(tutor_id=owner)
    other = student_factory(tutor_id=owner)
    with SessionLocal() as db:
        db.add(
            StudentAccess(
                student_id=other,
                login="other",
                email="busy@example.com",
                password_hash="pbkdf2_sha256$1$placeholder$placeholder",
            )
        )
        db.commit()
    token = _make_invite(owner, student_id)

    response = client.post(
        f"/invite/{token}",
        data={"email": "busy@example.com", "password": "пароль-пароль"},
    )
    assert "уже используется" in response.text
    with SessionLocal() as db:
        assert db.query(StudentAccess).filter_by(student_id=student_id).count() == 0


def test_register_invalid_tokens_same_message(client, owner, student_factory):
    """Неизвестный, погашенный и просроченный токен — одно сообщение (D9)."""
    student_id = student_factory(tutor_id=owner)

    unknown = client.get("/invite/нет-такого-токена").text
    assert "недействительна" in unknown
    assert 'name="email"' not in unknown

    token = _make_invite(owner, student_id)
    client.post(
        f"/invite/{token}",
        data={"email": "masha@example.com", "password": "пароль-пароль"},
        follow_redirects=False,
    )
    consumed = client.get(f"/invite/{token}").text
    assert "недействительна" in consumed
    assert "Секретное" not in consumed

    student2 = student_factory(tutor_id=owner)
    expired_token = _make_invite(owner, student2, token="expired-token")
    _expire_invite(expired_token)
    expired = client.get(f"/invite/{expired_token}").text
    assert "недействительна" in expired


# --------------------------------------------------------------------------
# 5.2 Вход в кабинет
# --------------------------------------------------------------------------


def _create_access(student_id: str, *, login: str, email: str | None, password: str):
    with SessionLocal() as db:
        db.add(
            StudentAccess(
                student_id=student_id,
                login=login,
                email=email,
                password_hash=PasswordHasher().hash(password),
            )
        )
        db.commit()


def test_login_by_email(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner)
    _create_access(student_id, login="petya", email="petya@example.com", password=PASSWORD)

    response = client.post(
        "/student/login",
        data={"identifier": "petya@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/student"


def test_login_by_login(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner)
    _create_access(student_id, login="petya", email="petya@example.com", password=PASSWORD)

    response = client.post(
        "/student/login",
        data={"identifier": "petya", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/student"


def test_login_wrong_password_generic_error(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner)
    _create_access(student_id, login="petya", email=None, password=PASSWORD)

    page = client.post(
        "/student/login",
        data={"identifier": "petya", "password": "неверный-пароль"},
    ).text
    assert "Неверный логин (email) или пароль" in page
    assert client.get("/student", follow_redirects=False).status_code == 303


# --------------------------------------------------------------------------
# 5.3 Кабинет и выход
# --------------------------------------------------------------------------


def test_cabinet_requires_session(client):
    """Без сессии ученика кабинет недоступен — редирект на вход."""
    response = client.get("/student", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/student/login"


def test_cabinet_uses_crm_shell(client, owner, student_factory):
    """Кабинет построен как кабинет репетитора (решение владельца 2026-10-30):
    сайдбар с меню и переключателем темы, мобильная шапка, строка ученика."""
    student_id = student_factory(tutor_id=owner, first_name="Аня", last_name="Ахматова")
    with SessionLocal() as db:
        token = create_session(db, student_id)
    client.cookies.set("student_session", token)

    page = client.get("/student").text

    # Сайдбар: активный пункт «Мои уроки» и заглушки будущих разделов.
    assert "Кабинет ученика" in page
    assert "nav-item--active" in page
    assert "Мои уроки" in page
    assert "nav-item--disabled" in page
    assert "Домашние задания" in page
    assert "Профиль" in page
    # Переключатель темы — те же кнопки, что у репетитора (app.js).
    assert 'data-theme-toggle="dark"' in page
    assert 'data-theme-toggle="light"' in page
    # Строка пользователя — имя ученика, выход в `/student/logout`.
    assert "Аня Ахматова" in page
    assert 'action="/student/logout"' in page
    # CRM-каркас: мобильная шапка и контент в `.main`.
    assert 'class="mobile-header"' in page
    assert 'class="main"' in page


def test_login_page_has_no_sidebar(client):
    """Вход и регистрация — поверхности «до входа», как у репетитора: без сайдбара."""
    assert 'class="sidebar"' not in client.get("/student/login").text
    assert "Мои уроки" not in client.get("/student/login").text


def test_cabinet_shows_my_lessons(client, owner, student_factory, lesson_factory):
    """«Мои уроки»: ближайшее занятие и список; чужие уроки не видны (6.1)."""
    student_a = student_factory(tutor_id=owner, first_name="Аня")
    student_b = student_factory(tutor_id=owner, first_name="Борис")
    lesson_factory(
        student_id=student_a,
        status="planned",
        starts_at=datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )
    lesson_factory(
        student_id=student_b,
        status="planned",
        starts_at=datetime(2027, 3, 2, 12, 0, tzinfo=UTC),
    )

    with SessionLocal() as db:
        token = create_session(db, student_a)

    client.cookies.set("student_session", token)
    page = client.get("/student").text

    assert "Мои уроки" in page
    assert "Ближайшее занятие" in page
    assert "01.03.2027" in page
    # Урок ученика B (даже того же репетитора) не попадает в кабинет A.
    assert "02.03.2027" not in page


def test_cabinet_group_lesson_visible(client, owner, student_factory, lesson_factory,
                                       group_factory, group_member_factory):
    """Групповой урок показан наравне с индивидуальными."""
    student_id = student_factory(tutor_id=owner)
    group_id = group_factory()
    group_member_factory(group_id=group_id, student_id=student_id)
    lesson_factory(
        group_id=group_id,
        status="planned",
        starts_at=datetime(2027, 4, 5, 15, 0, tzinfo=UTC),
    )

    with SessionLocal() as db:
        token = create_session(db, student_id)
    client.cookies.set("student_session", token)

    page = client.get("/student").text
    assert "05.04.2027" in page
    assert "Групповой" in page


def test_cabinet_empty_when_all_lessons_past(client, owner, student_factory, lesson_factory):
    """Все уроки в прошлом — список пуст, прошедшие не показываются."""
    student_id = student_factory(tutor_id=owner)
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2020, 1, 1, 10, 0, tzinfo=UTC),
    )

    with SessionLocal() as db:
        token = create_session(db, student_id)
    client.cookies.set("student_session", token)

    page = client.get("/student").text
    assert "Запланированных занятий пока нет" in page
    assert "01.01.2020" not in page


def test_logout_revokes_session(client, owner, student_factory):
    """Выход: сессия отозвана, повторное открытие кабинета ведёт на вход."""
    student_id = student_factory(tutor_id=owner)
    with SessionLocal() as db:
        token = create_session(db, student_id)
    client.cookies.set("student_session", token)

    response = client.post("/student/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/student/login"

    client.cookies.set("student_session", token)
    assert client.get("/student", follow_redirects=False).status_code == 303


# --------------------------------------------------------------------------
# 6.2 Независимость сессий (D4)
# --------------------------------------------------------------------------


def test_student_and_tutor_sessions_coexist(client, owner, student_factory):
    """Вход ученика не затрагивает сессию репетитора и наоборот."""
    student_id = student_factory(tutor_id=owner)
    with SessionLocal() as db:
        token = create_session(db, student_id)

    # Вход ученика в браузере, где репетитор уже залогинен.
    response = client.post(
        "/student/login",
        data={"identifier": "x", "password": "x"},
        follow_redirects=False,
    )
    client.cookies.set("student_session", token)

    cookies = client.cookies
    assert "student_session" in cookies
    assert "tutor_session" in cookies

    # Обе сессии работают одновременно: страница репетитора и кабинет.
    assert client.get("/tutor/", follow_redirects=False).status_code == 200
    assert client.get("/student", follow_redirects=False).status_code == 200

    # Выход ученика — сессия репетитора жива.
    client.post("/student/logout", follow_redirects=False)
    assert client.get("/tutor/", follow_redirects=False).status_code == 200
    assert client.get("/student", follow_redirects=False).status_code == 303

    # Выход репетитора — кабинет с вновь выданной сессией ученика жив.
    with SessionLocal() as db:
        fresh = create_session(db, student_id)
    client.cookies.set("student_session", fresh)
    client.post("/tutor/logout", follow_redirects=False)
    assert client.get("/student", follow_redirects=False).status_code == 200
    assert client.get("/tutor/", follow_redirects=False).status_code == 303
