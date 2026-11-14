"""Тесты приветственных писем при регистрации (TOCRM-69).

Проверяем три сценария регистрации — репетитор, ученик по приглашению,
родитель по приглашению: письмо уходит на указанный email, тема и шаблон
соответствуют роли, в HTML подставлено имя, отправка одна и в фоне, а
ошибка транспорта не меняет ответ регистрации.

Транспорт подменяется на уровне сервиса: `TestClient` выполняет
`BackgroundTasks` при обработке ответа, поэтому реальный SMTP не нужен.
"""

from pathlib import Path

import pytest

from app.cabinet.models.contact_invite import ContactCabinetInvite
from app.cabinet.models.invite import StudentCabinetInvite
from app.cabinet.services.contact_invites import create_invite as create_contact_invite
from app.cabinet.services.invites import create_invite as create_student_invite
from app.common import email_subjects
from app.common.services import welcome_email
from app.database import SessionLocal
from app.student.models.contact import Contact
from app.tutor.models.tutor import Tutor

PASSWORD = "Секретный-Пароль-1"
TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent / "app" / "common" / "templates" / "email"
)

TUTOR_FORM = {
    "name": "Мария Сидорова",
    "email": "maria@example.com",
    "password": PASSWORD,
    "password_confirm": PASSWORD,
}


@pytest.fixture()
def sent(monkeypatch):
    """Перехватывает `send_email` сервиса и запоминает вызовы."""
    calls: list[dict] = []

    def fake_send_email(*, to_email, subject, html, text=None):
        calls.append(
            {"to_email": to_email, "subject": subject, "html": html, "text": text}
        )
        return []

    monkeypatch.setattr(welcome_email, "send_email", fake_send_email)
    return calls


def _student_invite(tutor_id: str, student_id: str, token: str = "welcome-student") -> str:
    with SessionLocal() as db:
        create_student_invite(db, tutor_id, student_id)
        invite = db.query(StudentCabinetInvite).filter_by(student_id=student_id).one()
        invite.token = token
        db.commit()
        return invite.token


def _contact_invite(contact_id: str, token: str = "welcome-parent") -> str:
    with SessionLocal() as db:
        contact_row = db.get(Contact, contact_id)
        create_contact_invite(db, contact_row.tutor_id, contact_id)
        invite = (
            db.query(ContactCabinetInvite).filter_by(contact_id=contact_id).one()
        )
        invite.token = token
        db.commit()
        return invite.token


# --------------------------------------------------------------------------
# Сервис: шаблон, тема, имя
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("role", "template", "subject"),
    [
        ("tutor", "welcome_tutor.html.jinja2", email_subjects.WELCOME_TUTOR),
        ("student", "welcome_student.html.jinja2", email_subjects.WELCOME_STUDENT),
        ("parent", "welcome_parent.html.jinja2", email_subjects.WELCOME_PARENT),
    ],
)
def test_roles_have_own_template_and_subject(role, template, subject):
    """У каждой роли — свой файл шаблона в репозитории и своя тема."""
    assert welcome_email.welcome_template_path(role) == f"email/{template}"
    assert (TEMPLATES_DIR / template).is_file()
    assert welcome_email.WELCOME_EMAILS[role][1] == subject


def test_subject_constants_match_acceptance():
    """Формулировки тем зафиксированы требованием задачи."""
    assert email_subjects.WELCOME_TUTOR == "Добро пожаловать в Open Tutor CRM"
    assert email_subjects.WELCOME_STUDENT == (
        "Добро пожаловать в личный кабинет ученика"
    )
    assert email_subjects.WELCOME_PARENT == "Добро пожаловать в кабинет родителя"


@pytest.mark.parametrize("role", ["tutor", "student", "parent"])
def test_sends_html_rendered_from_repository_template(role, sent):
    """Письмо — HTML из файла шаблона, имя подставлено, отправка одна."""
    errors = welcome_email.send_welcome_email(
        role=role, to_email="user@example.com", user_name="Иван Петров"
    )
    assert errors == []
    assert len(sent) == 1

    message = sent[0]
    assert message["to_email"] == "user@example.com"
    assert message["subject"] == welcome_email.WELCOME_EMAILS[role][1]
    assert "Иван Петров" in message["html"]
    assert "<html" in message["html"]

    # Фраза из файла шаблона: правка репозитория попадает в письмо без
    # изменений в коде — рендерится именно файл, а не строка в Python.
    template_name = welcome_email.welcome_template_path(role).split("/", 1)[1]
    source = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    heading = next(
        line.strip() for line in source.splitlines() if "<h1" in line
    )
    heading_text = heading.split(">", 1)[1].split("<", 1)[0]
    assert heading_text in message["html"]


def test_empty_name_falls_back_to_neutral_greeting(sent):
    """Пустое имя не оставляет в письме «Здравствуйте, !»."""
    welcome_email.send_welcome_email(
        role="tutor", to_email="user@example.com", user_name="  "
    )
    assert "Здравствуйте, друг!" in sent[0]["html"]


# --------------------------------------------------------------------------
# Регистрация: фоновая задача и получатель
# --------------------------------------------------------------------------

def test_tutor_registration_sends_welcome_email(client, sent):
    response = client.post("/tutor/register", data=TUTOR_FORM, follow_redirects=False)

    assert response.status_code == 303
    assert len(sent) == 1
    assert sent[0]["to_email"] == "maria@example.com"
    assert sent[0]["subject"] == email_subjects.WELCOME_TUTOR
    assert "Мария Сидорова" in sent[0]["html"]


def test_failed_tutor_registration_does_not_send(client, sent):
    """Ошибка формы (дубликат email) не ставит задачу отправки."""
    client.post("/tutor/register", data=TUTOR_FORM, follow_redirects=False)
    sent.clear()

    response = client.post(
        "/tutor/register",
        data={**TUTOR_FORM, "name": "Другой Человек"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert sent == []


def test_student_registration_sends_welcome_email(
    client, tutor_factory, student_factory, sent
):
    tutor_id = tutor_factory()
    student_id = student_factory(
        tutor_id=tutor_id, first_name="Мария", last_name="Иванова"
    )
    token = _student_invite(tutor_id, student_id)

    response = client.post(
        f"/invite/{token}",
        data={"email": "masha@example.com", "password": "пароль-пароль"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert len(sent) == 1
    assert sent[0]["to_email"] == "masha@example.com"
    assert sent[0]["subject"] == email_subjects.WELCOME_STUDENT
    # Имя — из карточки ученика: форма его не спрашивает.
    assert "Мария Иванова" in sent[0]["html"]


def test_parent_registration_sends_welcome_email(
    client, tutor_factory, contact_factory, sent
):
    tutor_id = tutor_factory()
    contact_id = contact_factory(tutor_id=tutor_id, full_name="Ольга Петрова")
    token = _contact_invite(contact_id)

    response = client.post(
        f"/parent/invite/{token}",
        data={"email": "mama@example.com", "password": "пароль-пароль"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert len(sent) == 1
    assert sent[0]["to_email"] == "mama@example.com"
    assert sent[0]["subject"] == email_subjects.WELCOME_PARENT
    assert "Ольга Петрова" in sent[0]["html"]


def test_invalid_invite_does_not_send(client, sent):
    response = client.post(
        "/invite/нет-такого-токена",
        data={"email": "masha@example.com", "password": "пароль-пароль"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert sent == []


# --------------------------------------------------------------------------
# Ошибка отправки: регистрация не ломается, причина — в лог
# --------------------------------------------------------------------------

def test_delivery_error_is_logged_and_registration_succeeds(
    client, monkeypatch, caplog
):
    """Сбой SMTP не влияет на HTTP-ответ; причина пишется в лог."""
    calls: list[dict] = []

    def failing_send_email(*, to_email, subject, html, text=None):
        calls.append({"to_email": to_email, "subject": subject})
        return ["Не удалось связаться с почтовым сервером: timeout"]

    monkeypatch.setattr(welcome_email, "send_email", failing_send_email)

    with caplog.at_level("WARNING", logger="mail"):
        response = client.post(
            "/tutor/register", data=TUTOR_FORM, follow_redirects=False
        )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/tutor/login")
    # Одна попытка: повторов нет.
    assert len(calls) == 1
    with SessionLocal() as db:
        assert db.query(Tutor).filter_by(email="maria@example.com").one()
    assert any(
        "не отправлено" in record.getMessage() for record in caplog.records
    )


def test_disabled_mail_still_registers_and_logs(client, caplog):
    """Почта не настроена — регистрация проходит, причина в логе."""
    with caplog.at_level("WARNING", logger="mail"):
        response = client.post(
            "/tutor/register", data=TUTOR_FORM, follow_redirects=False
        )

    assert response.status_code == 303
    assert any(
        "не настроена" in record.getMessage() for record in caplog.records
    )


# --------------------------------------------------------------------------
# Reply-To в конфигурации и сборке письма
# --------------------------------------------------------------------------

def test_reply_to_header_is_set_from_settings(monkeypatch):
    from app.mail.services import sender

    monkeypatch.setattr(sender.settings, "smtp_from", "bot@example.com")
    monkeypatch.setattr(sender.settings, "smtp_reply_to", "support@example.com")
    message = sender.build_message(
        to_email="user@example.com", subject="Тема", html="<p>Привет</p>"
    )
    assert message["Reply-To"] == "support@example.com"


def test_reply_to_header_is_omitted_when_not_configured(monkeypatch):
    from app.mail.services import sender

    monkeypatch.setattr(sender.settings, "smtp_from", "bot@example.com")
    monkeypatch.setattr(sender.settings, "smtp_reply_to", "")
    message = sender.build_message(
        to_email="user@example.com", subject="Тема", html="<p>Привет</p>"
    )
    assert message["Reply-To"] is None
