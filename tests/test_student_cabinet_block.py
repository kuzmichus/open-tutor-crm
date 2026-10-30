"""Тесты блока «Личный кабинет» в карточке ученика (change
student-cabinet-access): три состояния рендера, отсутствие блока у нового
ученика, маршрут приглашения (htmx / без JS), изоляция по репетитору.
"""

import pytest
from datetime import UTC, datetime, timedelta

from app.database import SessionLocal
from app.cabinet.models.invite import StudentCabinetInvite
from app.student.models.student_access import StudentAccess


PASSWORD = "Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="cabinet-block-owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "cabinet-block-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _open_card(client, student_id: str, tab: str = "settings"):
    """Открывает модалку карточки на вкладке «Настройки» (как пользователь)."""
    return client.get(f"/tutor/students/{student_id}/edit?tab={tab}").text


def test_block_without_access_shows_note_and_button(client, owner, student_factory):
    """Состояние «нет входа»: заметка с именем и кнопка «Создать приглашение»."""
    student_id = student_factory(tutor_id=owner, first_name="Маша", last_name="Иванова")
    page = _open_card(client, student_id)

    assert "Личный кабинет" in page
    assert "пока не привязан ни один вход" in page
    assert "Маша Иванова" in page
    assert "Создать приглашение" in page
    assert "/invite/" not in page


def test_block_with_active_invite_shows_link(client, owner, tutor_factory, student_factory):
    """Состояние «ссылка активна»: полный адрес для отправки и копирование."""
    student_id = student_factory(tutor_id=owner)
    with SessionLocal() as db:
        db.add(
            StudentCabinetInvite(
                tutor_id=owner,
                student_id=student_id,
                token="cabinet-test-token",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        db.commit()

    page = _open_card(client, student_id)
    assert "/invite/cabinet-test-token" in page
    assert "Отправьте эту ссылку ученику. Она действует 7 дней." in page
    assert "Скопировать ссылку" in page


def test_block_with_access_shows_identifiers(client, owner, tutor_factory, student_factory):
    """Состояние «вход привязан»: идентификаторы входа, приглашение доступно."""
    student_id = student_factory(tutor_id=owner)
    with SessionLocal() as db:
        db.add(
            StudentAccess(
                student_id=student_id,
                login="masha",
                email="masha@example.com",
                password_hash="pbkdf2_sha256$1$placeholder$placeholder",
            )
        )
        db.commit()

    page = _open_card(client, student_id)
    assert "Вход привязан" in page
    assert "masha@example.com" in page
    # Логин равен email? Нет — вход ручной: показываются оба идентификатора.
    assert "Логин: masha" in page
    assert "Создать приглашение" in page


def test_block_absent_for_new_student(client, owner):
    """У формы создания нового ученика блока нет."""
    page = client.get("/tutor/students/new").text
    assert "Личный кабинет" not in page


def test_invite_route_returns_updated_block(client, owner, student_factory):
    """POST по htmx: ответ — обновлённый блок со ссылкой; в БД приглашение."""
    student_id = student_factory(tutor_id=owner)
    response = client.post(
        f"/tutor/students/{student_id}/cabinet/invite",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "/invite/" in response.text
    assert "Отправьте эту ссылку ученику" in response.text

    with SessionLocal() as db:
        assert db.query(StudentCabinetInvite).filter_by(student_id=student_id).count() == 1


def test_invite_route_without_htmx_redirects(client, owner, student_factory):
    """Без JS — 303 на карточку: форма работает и без htmx."""
    student_id = student_factory(tutor_id=owner)
    response = client.post(
        f"/tutor/students/{student_id}/cabinet/invite",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/tutor/students/{student_id}"


def test_invite_route_isolation(client, owner, tutor_factory, student_factory):
    """Чужой ученик и несуществующий неразличимы — 404; приглашения нет."""
    other_id = tutor_factory(email="cabinet-block-other@example.com")
    foreign = student_factory(tutor_id=other_id)

    response = client.post(
        f"/tutor/students/{foreign}/cabinet/invite",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 404
    assert client.post("/tutor/students/нет-такого/cabinet/invite").status_code == 404

    with SessionLocal() as db:
        assert db.query(StudentCabinetInvite).count() == 0


def test_invite_reissue_replaces_link(client, owner, student_factory):
    """Перевыпуск: прежняя ссылка перестаёт работать, новая активна."""
    student_id = student_factory(tutor_id=owner)
    client.post(
        f"/tutor/students/{student_id}/cabinet/invite",
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as db:
        old_token = db.query(StudentCabinetInvite).filter_by(
            student_id=student_id
        ).one().token

    client.post(
        f"/tutor/students/{student_id}/cabinet/invite",
        headers={"HX-Request": "true"},
    )
    with SessionLocal() as db:
        invites = db.query(StudentCabinetInvite).filter_by(student_id=student_id).all()
        assert len(invites) == 1
        new_token = invites[0].token

    assert old_token != new_token
    page = _open_card(client, student_id)
    assert f"/invite/{new_token}" in page
    assert old_token not in page
