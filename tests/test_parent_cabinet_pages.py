"""Тесты страниц кабинета родителя (change parent-cabinet).

Регистрация по приглашению, вход, каркас `/parent` с секциями по детям,
вкладки ребёнка (уроки, домашние задания), «Финансы», «Профиль», выход;
бейдж «Личный кабинет» на миникарточке контакта; изоляция контактов и
независимость трёх сессий (репетитор, ученик, родитель) в одном браузере.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.cabinet.models.contact_invite import ContactCabinetInvite
from app.cabinet.services.contact_invites import create_invite
from app.database import SessionLocal
from app.student.models.contact import Contact
from app.student.models.student_contact import StudentContact
from app.tutor.services.password_hasher import PasswordHasher

PASSWORD = "Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="parent-owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "parent-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _link(student_id: str, contact_id: str) -> None:
    with SessionLocal() as db:
        db.add(StudentContact(student_id=student_id, contact_id=contact_id))
        db.commit()


def _make_contact(tutor_id: str, full_name: str = "Мария Смирнова") -> str:
    with SessionLocal() as db:
        contact = Contact(tutor_id=tutor_id, full_name=full_name)
        db.add(contact)
        db.commit()
        return contact.id


def _make_contact_invite(contact_id: str, token: str = "parent-page-token") -> str:
    """Перевыпускает приглашение контакта с фиксированным токеном."""
    with SessionLocal() as db:
        contact = db.get(Contact, contact_id)
        create_invite(db, contact.tutor_id, contact_id)
        invite = (
            db.query(ContactCabinetInvite).filter_by(contact_id=contact_id).one()
        )
        invite.token = token
        db.commit()
        return invite.token


def _expire_invite(token: str) -> None:
    with SessionLocal() as db:
        invite = db.query(ContactCabinetInvite).filter_by(token=token).one()
        invite.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()


# --------------------------------------------------------------------------
# 4.1 Регистрация по приглашению
# --------------------------------------------------------------------------


def test_parent_register_page_shows_only_email_and_password(
    client, owner, contact_factory
):
    """Публичная форма: Email и Пароль; имени контакта и детей нет."""
    contact_id = _make_contact(owner, full_name="Секретный Контакт")
    token = _make_contact_invite(contact_id)

    page = client.get(f"/parent/invite/{token}").text
    assert 'name="email"' in page
    assert 'name="password"' in page
    assert "Секретный" not in page
    assert "Контакт" not in page
    # Публичность: без сессий репетитора/ученика/родителя в разметке.
    assert "parent_session" not in page


def test_parent_register_creates_access_and_session(client, owner, contact_factory):
    contact_id = _make_contact(owner)
    token = _make_contact_invite(contact_id)

    response = client.post(
        f"/parent/invite/{token}",
        data={"email": "mama@example.com", "password": "пароль-пароль"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/parent"
    # Сессия родителя выдана, кабинет открывается.
    assert client.get("/parent").status_code == 200


def test_parent_register_updates_existing_access(client, owner, contact_factory):
    """Повторная регистрация по перевыпущенной ссылке обновляет вход."""
    contact_id = _make_contact(owner)
    first_token = _make_contact_invite(contact_id)
    client.post(
        f"/parent/invite/{first_token}",
        data={"email": "old@example.com", "password": "старый-пароль"},
    )

    # Перевыпуск: прежняя ссылка гасится, новая регистрирует тот же вход.
    second_token = _make_contact_invite(contact_id, token="parent-second-token")
    response = client.post(
        f"/parent/invite/{second_token}",
        data={"email": "new@example.com", "password": "новый-пароль"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        from app.cabinet.models.contact_access import ContactAccess

        rows = (
            db.query(ContactAccess).filter_by(contact_id=contact_id).all()
        )
    assert len(rows) == 1
    assert rows[0].email == "new@example.com"
    assert PasswordHasher().verify("новый-пароль", rows[0].password_hash)


def test_parent_register_rejects_taken_email(client, owner, contact_factory):
    first = _make_contact(owner)
    second = _make_contact(owner)
    client.post(
        f"/parent/invite/{_make_contact_invite(first)}",
        data={"email": "занят@example.com", "password": "пароль-пароль"},
    )

    page = client.post(
        f"/parent/invite/{_make_contact_invite(second, token='parent-taken-token')}",
        data={"email": "занят@example.com", "password": "пароль-пароль"},
    ).text
    assert "уже используется" in page


def test_parent_register_invalid_tokens_same_message(client, owner, contact_factory):
    """Неизвестный, погашенный и просроченный токен — одно сообщение."""
    contact_id = _make_contact(owner)
    used = _make_contact_invite(contact_id, token="parent-used-token")
    client.post(
        f"/parent/invite/{used}",
        data={"email": "mama@example.com", "password": "пароль-пароль"},
    )
    expired = _make_contact_invite(contact_id, token="parent-expired-token")
    _expire_invite(expired)

    known = "Ссылка недействительна"
    assert known in client.get("/parent/invite/нет-такого-токена").text
    assert known in client.get(f"/parent/invite/{used}").text
    assert known in client.get(f"/parent/invite/{expired}").text
    # Имя контакта на странице ошибки не раскрывается.
    assert "Мария" not in client.get("/parent/invite/нет-такого-токена").text


# --------------------------------------------------------------------------
# 4.2 Вход в кабинет родителя
# --------------------------------------------------------------------------


def _seed_parent_access(contact_id: str, email: str = "mama@example.com") -> None:
    with SessionLocal() as db:
        from app.cabinet.models.contact_access import ContactAccess

        db.add(
            ContactAccess(
                contact_id=contact_id,
                email=email,
                password_hash=PasswordHasher().hash(PASSWORD),
            )
        )
        db.commit()


def test_parent_login_success(client, owner, contact_factory):
    contact_id = _make_contact(owner)
    _seed_parent_access(contact_id)

    response = client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/parent"
    assert client.get("/parent").status_code == 200


def test_parent_login_wrong_password_generic_error(client, owner, contact_factory):
    contact_id = _make_contact(owner)
    _seed_parent_access(contact_id)

    page = client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": "не-тот-пароль"},
    ).text
    assert "Неверный email или пароль" in page
    # Кабинет не открыт.
    assert client.get("/parent", follow_redirects=False).status_code == 303


# --------------------------------------------------------------------------
# 5.1 Каркас кабинета
# --------------------------------------------------------------------------


def test_parent_cabinet_requires_session(client):
    assert client.get("/parent", follow_redirects=False).status_code == 303
    assert (
        client.get("/parent", follow_redirects=False).headers["location"]
        == "/parent/login"
    )


def test_parent_cabinet_sections_per_child(client, owner, student_factory, contact_factory):
    """Секция на каждого ребёнка: имя и ссылки его страниц; общий итог."""
    contact_id = _make_contact(owner)
    first = student_factory(tutor_id=owner, first_name="Аня")
    second = student_factory(tutor_id=owner, first_name="Боря")
    archived = student_factory(
        tutor_id=owner, first_name="Вера", status="archived"
    )
    for student in (first, second, archived):
        _link(student, contact_id)
    _seed_parent_access(contact_id)
    client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
    )

    page = client.get("/parent").text
    assert "Кабинет родителя" in page
    for name in ("Аня", "Боря", "Вера"):
        assert name in page
    assert f'href="/parent/students/{first}"' in page
    assert f'href="/parent/students/{first}/homework"' in page
    assert f'href="/parent/students/{second}"' in page
    assert 'href="/parent/finance"' in page
    assert 'href="/parent/profile"' in page
    # Архивный ребёнок наравне с активными (D5).
    assert f'href="/parent/students/{archived}"' in page


def test_parent_cabinet_without_children_common_items(client, owner, contact_factory):
    contact_id = _make_contact(owner)
    _seed_parent_access(contact_id)
    client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
    )

    page = client.get("/parent").text
    assert "Кабинет родителя" in page
    assert 'href="/parent/finance"' in page
    assert 'href="/parent/profile"' in page
    # Выход — форма POST в сайдбаре.
    assert 'action="/parent/logout"' in page


# --------------------------------------------------------------------------
# 5.2 Вкладка ребёнка «Мои уроки»
# --------------------------------------------------------------------------


def test_parent_child_lessons_nearest_first_no_past(
    client, owner, student_factory, contact_factory, lesson_factory
):
    contact_id = _make_contact(owner)
    student_id = student_factory(tutor_id=owner)
    _link(student_id, contact_id)
    _seed_parent_access(contact_id)
    client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
    )

    # Прошедший урок не показывается; из будущих ближайший — первый.
    lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
    )
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
    )
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2026, 11, 10, 10, 0, tzinfo=UTC),
    )

    page = client.get(f"/parent/students/{student_id}").text
    assert "Ближайшее занятие" in page
    assert "Запланированных занятий пока нет" not in page
    # Порядок дат в разметке: 10 ноября раньше 20 ноября (формат
    # `lesson_date` — «ДД.ММ.ГГГГ»).
    assert page.index("10.11.2026") < page.index("20.11.2026")
    assert "01.10.2026" not in page


def test_parent_child_group_lesson_visible(
    client, owner, student_factory, group_factory, group_member_factory,
    lesson_factory, contact_factory,
):
    contact_id = _make_contact(owner)
    student_id = student_factory(tutor_id=owner)
    _link(student_id, contact_id)
    _seed_parent_access(contact_id)
    client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
    )

    group_id = group_factory(tutor_id=owner)
    group_member_factory(group_id=group_id, student_id=student_id)
    lesson_factory(
        group_id=group_id,
        student_id=None,
        status="planned",
        starts_at=datetime(2026, 11, 12, 10, 0, tzinfo=UTC),
    )

    page = client.get(f"/parent/students/{student_id}").text
    assert "Ближайшее занятие" in page


def test_parent_child_unlinked_student_404(client, owner, student_factory, contact_factory):
    contact_id = _make_contact(owner)
    _seed_parent_access(contact_id)
    client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
    )
    stranger = student_factory(tutor_id=owner)

    for url in (
        f"/parent/students/{stranger}",
        f"/parent/students/{stranger}/homework",
    ):
        assert client.get(url).status_code == 404


# --------------------------------------------------------------------------
# 5.3 Вкладка ребёнка «Домашние задания»
# --------------------------------------------------------------------------


def test_parent_child_homework_view_only_no_teacher_note(
    client, owner, student_factory, contact_factory, lesson_factory
):
    """Задания видны, заметки педагога в разметке нет, действий нет."""
    contact_id = _make_contact(owner)
    student_id = student_factory(tutor_id=owner)
    _link(student_id, contact_id)
    _seed_parent_access(contact_id)
    client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
    )

    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2026, 11, 5, 15, 0, tzinfo=UTC),
    )
    with SessionLocal() as db:
        from app.homework.models.homework import Homework

        db.add(
            Homework(
                lesson_id=lesson_id,
                assignment="Страница 12, упражнения 3–5",
                status="assigned",
                teacher_note="Секретная заметка педагога",
                teacher_comment="Комментарий для ученика",
            )
        )
        db.commit()

    page = client.get(f"/parent/students/{student_id}/homework").text
    assert "Страница 12, упражнения 3–5" in page
    assert "Комментарий для ученика" in page
    assert "Задано" in page
    # Заметка педагога скрыта от ученика — родителю не показывается.
    assert "Секретная заметка" not in page
    # Только просмотр: в контенте страницы нет формы ответа (форма выхода
    # живёт в сайдбаре, проверяем содержимое <main>).
    main_html = page[page.index("<main") : page.index("</main>")]
    assert "hw-answer" not in main_html
    assert "<form" not in main_html


# --------------------------------------------------------------------------
# 5.4 Вкладка «Финансы»
# --------------------------------------------------------------------------


def test_parent_finance_blocks_and_total(
    client, owner, student_factory, contact_factory, operation_factory
):
    """Двое детей — два блока с их операциями; итог суммирует; плательщик не назначен."""
    contact_id = _make_contact(owner)
    first = student_factory(tutor_id=owner, first_name="Аня")
    second = student_factory(tutor_id=owner, first_name="Боря")
    _link(first, contact_id)
    _link(second, contact_id)
    _seed_parent_access(contact_id)
    client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
    )

    operation_factory(student_id=first, kind="payment", amount=3000, status="paid")
    operation_factory(student_id=second, kind="payment", amount=1500, status="paid")
    operation_factory(student_id=second, kind="lesson", amount=600)

    page = client.get("/parent/finance").text
    for name in ("Аня", "Боря"):
        assert name in page
    assert "Общий баланс" in page
    # Итог: 3000 + (1500 − 600) = 3 900 ₽ (money() — неразрывные пробелы).
    assert "3\u00a0900\u00a0₽" in page
    # Операции каждого ребёнка в его блоке: подпись списания и сумма.
    assert "Урок" in page
    assert "600\u00a0₽" in page


# --------------------------------------------------------------------------
# 5.5 Вкладка «Профиль»
# --------------------------------------------------------------------------


def test_parent_profile_shows_contact_data_without_forms(
    client, owner, contact_factory
):
    contact_id = _make_contact(owner, full_name="Ольга Петрова")
    with SessionLocal() as db:
        contact = db.get(Contact, contact_id)
        contact.phone = "+7 555 000-11-22"
        contact.email = "olga@example.com"
        db.commit()
    _seed_parent_access(contact_id, email="olga-login@example.com")
    client.post(
        "/parent/login",
        data={"email": "olga-login@example.com", "password": PASSWORD},
    )

    page = client.get("/parent/profile").text
    for value in (
        "Ольга Петрова",
        "+7 555 000-11-22",
        "olga@example.com",
        "olga-login@example.com",
    ):
        assert value in page
    # Режим просмотра: действий изменения нет (форма выхода живёт в
    # сайдбаре, проверяем карточку профиля).
    card_html = page[
        page.index('class="card parent-profile"') : page.index("</section>")
    ]
    assert 'method="post"' not in card_html
    assert "<input" not in card_html


# --------------------------------------------------------------------------
# 5.6 Выход
# --------------------------------------------------------------------------


def test_parent_logout_revokes_session(client, owner, contact_factory):
    contact_id = _make_contact(owner)
    _seed_parent_access(contact_id)
    client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
    )
    assert client.get("/parent").status_code == 200

    response = client.post("/parent/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/parent/login"
    assert client.get("/parent", follow_redirects=False).status_code == 303


# --------------------------------------------------------------------------
# 3.1–3.2 Бейдж «Личный кабинет» на миникарточке контакта
# --------------------------------------------------------------------------


def test_contact_badge_invite_action_returns_fragment_with_link(
    client, owner, contact_factory
):
    contact_id = _make_contact(owner)
    response = client.post(
        f"/tutor/contacts/{contact_id}/cabinet/invite",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "/parent/invite/" in response.text
    assert "действует 7 дней" in response.text
    # Это фрагмент бейджа, а не страница: разметка строки контакта не
    # приезжает целиком.
    assert "<!DOCTYPE html>" not in response.text


def test_contact_badge_foreign_contact_404(client, owner, tutor_factory, contact_factory):
    stranger_tutor = tutor_factory()
    foreign = _make_contact(stranger_tutor)
    assert (
        client.post(f"/tutor/contacts/{foreign}/cabinet/invite").status_code == 404
    )


def test_contact_badge_three_states_in_student_form(
    client, owner, student_factory, contact_factory
):
    """Три состояния в форме ученика; у несохранённой строки бейджа нет."""
    bare = _make_contact(owner)
    invited = _make_contact(owner)
    bound = _make_contact(owner)
    student_id = student_factory(tutor_id=owner)
    for contact in (bare, invited, bound):
        _link(student_id, contact)
    _make_contact_invite(invited, token="badge-active-token")
    _seed_parent_access(bound, email="bound@example.com")

    page = client.get(f"/tutor/students/{student_id}/edit").text

    # Без входа: кнопка «Создать приглашение».
    assert f'id="contact-cabinet-{bare}"' in page
    bare_start = page.index(f'id="contact-cabinet-{bare}"')
    bare_end = page.index('class="contact-suggestion"', bare_start)
    assert "Создать приглашение" in page[bare_start:bare_end]

    # Ссылка активна: адрес и пометка о сроке.
    invited_start = page.index(f'id="contact-cabinet-{invited}"')
    invited_end = page.index('class="contact-suggestion"', invited_start)
    assert "/parent/invite/badge-active-token" in page[invited_start:invited_end]
    assert "действует 7 дней" in page[invited_start:invited_end]

    # Вход привязан: email виден, создание приглашения остаётся доступным
    # (у контакта в этом тесте активной ссылки нет — кнопка «Создать
    # приглашение», перевыпуск применяется к живой ссылке).
    bound_start = page.index(f'id="contact-cabinet-{bound}"')
    bound_end = page.index('class="contact-suggestion"', bound_start)
    assert "bound@example.com" in page[bound_start:bound_end]
    assert "Создать приглашение" in page[bound_start:bound_end]

    # Инертный шаблон строки (клон students.js) без бейджа: у клона нет
    # contact_id, он появится после сохранения и перезагрузки страницы.
    template_start = page.index('id="contact-row-template"')
    template_html = page[template_start : page.index("</template>", template_start)]
    assert "contact-cabinet" not in template_html


# --------------------------------------------------------------------------
# 6.1 Изоляция контактов
# --------------------------------------------------------------------------


def test_contact_session_cannot_open_other_contact_child(
    client, owner, student_factory, contact_factory
):
    """Сессия контакта A не открывает страницы ребёнка контакта B."""
    own_contact = _make_contact(owner)
    own_student = student_factory(tutor_id=owner, first_name="Аня")
    _link(own_student, own_contact)

    other_contact = _make_contact(owner)
    other_student = student_factory(tutor_id=owner, first_name="Боря")
    _link(other_student, other_contact)

    client.post(
        f"/parent/invite/{_make_contact_invite(own_contact, token='own-parent-token')}",
        data={"email": "own@example.com", "password": PASSWORD},
    )

    # Своё видно, чужое — 404 (неразличимо с несуществующим).
    assert client.get(f"/parent/students/{own_student}").status_code == 200
    assert client.get(f"/parent/students/{other_student}").status_code == 404
    assert (
        client.get(f"/parent/students/{other_student}/homework").status_code == 404
    )


def test_contact_action_between_tutors_isolated(
    client, owner, tutor_factory, contact_factory
):
    """Действие бейджа для контакта другого репетитора — 404 (два репетитора)."""
    other_tutor = tutor_factory(email="other-tutor@example.com", password=PASSWORD)
    foreign_contact = _make_contact(other_tutor)
    assert (
        client.post(f"/tutor/contacts/{foreign_contact}/cabinet/invite").status_code
        == 404
    )


# --------------------------------------------------------------------------
# 6.2 Независимость трёх сессий
# --------------------------------------------------------------------------


def test_three_sessions_coexist_in_one_client(
    client, owner, student_factory, contact_factory
):
    """Репетитор, ученик и родитель — три cookies, три кабинета одновременно."""
    student_id = student_factory(tutor_id=owner, first_name="Аня")

    contact_id = _make_contact(owner)
    _link(student_id, contact_id)
    _seed_parent_access(contact_id)
    parent_token = _make_contact_invite(contact_id, token="coexist-parent-token")
    client.post(
        f"/parent/invite/{parent_token}",
        data={"email": "mama@example.com", "password": PASSWORD},
    )

    # Ученик регистрируется по своему приглашению (сессия student_session).
    from app.cabinet.models.invite import StudentCabinetInvite
    from app.cabinet.services.invites import create_invite as create_student_invite

    with SessionLocal() as db:
        create_student_invite(db, owner, student_id)
        invite = (
            db.query(StudentCabinetInvite).filter_by(student_id=student_id).one()
        )
        student_token = invite.token
    client.post(
        f"/invite/{student_token}",
        data={"email": "anya@example.com", "password": PASSWORD},
    )

    # Все три поверхности работают в одном клиенте одновременно.
    assert client.get("/tutor/students").status_code == 200
    assert client.get("/student").status_code == 200
    assert client.get("/parent").status_code == 200

    # Выход родителя не трогает сессии репетитора и ученика.
    client.post("/parent/logout")
    assert client.get("/parent", follow_redirects=False).status_code == 303
    assert client.get("/tutor/students").status_code == 200
    assert client.get("/student").status_code == 200
