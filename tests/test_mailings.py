"""Тесты страницы «Коммуникации» (`/tutor/mailings`, спека mailing).

Поведение — через HTTP, теми же маршрутами, что у пользователя: разметка
ищется по тексту и атрибутам, отправка подменяет `urllib.request.urlopen`
(путь вызова тот же, что в бою, сеть не дёргается). Изоляция: чужие
ученики/шаблоны/журнал не видны, действия с чужими шаблонами — 404.
"""

import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.finance.services.presentation import balance_label
from app.mailing.models.message_template import MessageTemplate
from app.messenger.models.sent_message import SentMessage
from app.messenger.services.messengers import token_key
from app.tutor.services.params import set_param

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}

TELEGRAM_TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
MAX_TOKEN = "pKcfaXfFUnfTSMPSYJjpdHHnPEMucRQGxFYEXhIq"


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Минимальный ответ urlopen: context manager с JSON-телом."""

    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, responder, calls):
    """Подменяет urlopen; каждый вызов дописывается в список `calls`."""

    def fake_urlopen(request, timeout=None, context=None):
        calls.append(
            {
                "url": request.full_url,
                "data": json.loads(request.data.decode()),
            }
        )
        return responder(calls[-1])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _ok_responder(call):
    if "api.telegram.org" in call["url"]:
        return _FakeResponse({"ok": True, "result": {"message_id": 1}})
    return _FakeResponse({"message": {"body": {"text": call["data"]["text"]}}})


def _error_responder(call):
    if "api.telegram.org" in call["url"]:
        return _FakeResponse({"ok": False, "description": "chat not found"})
    raise urllib.error.HTTPError(
        call["url"], 400, "Bad Request", None,
        io.BytesIO('{"code": "chat.not.found", "message": "Чат не найден"}'.encode()),
    )


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="mailings-page@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "mailings-page@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def invite_factory(student_factory):
    """Завершённая привязка чата ученика; возвращает id приглашения."""

    def _create(
        student_id: str | None = None,
        messenger: str = "telegram",
        chat_id: str = "100200300",
        **extra,
    ):
        from app.messenger.models.student_invite import StudentMessengerInvite
        from app.student.models.student import Student

        if student_id is None:
            student_id = student_factory()
        with SessionLocal() as db:
            student = db.get(Student, student_id)
            invite = StudentMessengerInvite(
                tutor_id=student.tutor_id,
                student_id=student_id,
                messenger=messenger,
                chat_id=chat_id,
                **extra,
            )
            db.add(invite)
            db.commit()
            return invite.id

    return _create


@pytest.fixture()
def template_factory():
    """Создаёт шаблон сообщения; возвращает его id."""

    def _create(tutor_id: str, title: str = "Занятие", text: str = "Скоро занятие!"):
        with SessionLocal() as session:
            template = MessageTemplate(tutor_id=tutor_id, title=title, text=text)
            session.add(template)
            session.commit()
            return template.id

    return _create


def _stored_sent() -> list[SentMessage]:
    """Все строки журнала (в тесте — одна база на тест)."""
    with SessionLocal() as session:
        return list(session.scalars(select(SentMessage)).all())


def _connect_tokens(tutor_id: str, messengers=("telegram",)):
    """Сохраняет токены ботов (состояние «мессенджер подключён»)."""
    with SessionLocal() as db:
        if "telegram" in messengers:
            set_param(db, tutor_id, token_key("telegram"), TELEGRAM_TOKEN)
        if "max" in messengers:
            set_param(db, tutor_id, token_key("max"), MAX_TOKEN)


# ---------------------------------------------------------------------------
# Доступ и страница
# ---------------------------------------------------------------------------


def test_page_requires_login(client):
    response = client.get("/tutor/mailings", follow_redirects=False)
    assert response.status_code == 303
    assert "/tutor/login" in response.headers["location"]


def test_compose_page_renders(client, owner):
    response = client.get("/tutor/mailings")
    markup = response.text
    assert response.status_code == 200
    assert "Коммуникации" in markup
    assert "Новое сообщение" in markup
    assert "История" in markup
    assert "Текст сообщения" in markup
    assert "Фильтры" in markup
    assert "Должники" in markup
    assert "Были недавно (7 дней)" in markup
    assert "Без уроков" in markup
    assert "Отправить" in markup
    # Подсказка о подстановках видна на странице.
    assert "{имя}" in markup and "{баланс}" in markup


def test_history_tab_via_query(client, owner):
    response = client.get("/tutor/mailings?tab=history")
    assert response.status_code == 200
    assert "История сообщений бота" in response.text
    assert "Текст сообщения" not in response.text


def test_tab_partial_htmx(client, owner):
    response = client.get("/tutor/mailings/tabs/history", headers=HTMX)
    assert response.status_code == 200
    assert response.headers["HX-Push-Url"] == "/tutor/mailings?tab=history"
    assert "История сообщений бота" in response.text
    # Фрагмент, а не страница целиком.
    assert 'class="sidebar"' not in response.text


def test_tab_unknown_falls_back_to_compose(client, owner):
    response = client.get("/tutor/mailings/tabs/unknown", headers=HTMX)
    assert response.status_code == 200
    assert response.headers["HX-Push-Url"] == "/tutor/mailings"
    assert "Текст сообщения" in response.text


# ---------------------------------------------------------------------------
# Список получателей: поиск, сегменты, каналы
# ---------------------------------------------------------------------------


def test_recipients_search_by_name_and_phone(client, owner, student_factory):
    anya = student_factory(tutor_id=owner, first_name="Аня", phone="+7 900 111-22-33")
    student_factory(tutor_id=owner, first_name="Борис")

    by_name = client.get("/tutor/mailings/recipients?q=Аня", headers=HTMX).text
    assert "Аня" in by_name
    assert "Борис" not in by_name

    by_phone = client.get("/tutor/mailings/recipients?q=111-22-33", headers=HTMX).text
    assert "Аня" in by_phone


def test_recipients_segments(client, owner, student_factory, lesson_factory, operation_factory):
    """Сегменты: должник, будущий урок, недавний урок, без уроков.

    Имена персон не пересекаются с подписями чипов («Должники» видна в
    разметке любого сегмента — на имена и проверяем).
    """
    debtor = student_factory(tutor_id=owner, first_name="Анна")
    upcoming = student_factory(tutor_id=owner, first_name="Борис")
    recent = student_factory(tutor_id=owner, first_name="Вера")
    stale = student_factory(tutor_id=owner, first_name="Глеб")
    idle = student_factory(tutor_id=owner, first_name="Даша")

    operation_factory(student_id=debtor, kind="lesson", amount=3300, status=None)
    lesson_factory(
        student_id=upcoming,
        status="planned",
        starts_at=datetime.now(UTC) + timedelta(days=2),
    )
    lesson_factory(
        student_id=recent,
        status="completed",
        starts_at=datetime.now(UTC) - timedelta(days=3),
    )
    lesson_factory(
        student_id=stale,
        status="completed",
        starts_at=datetime.now(UTC) - timedelta(days=8),
    )

    debtors = client.get("/tutor/mailings/recipients?segment=debtors", headers=HTMX).text
    assert "Анна" in debtors
    assert "Борис" not in debtors and "Даша" not in debtors

    futures = client.get("/tutor/mailings/recipients?segment=upcoming", headers=HTMX).text
    assert "Борис" in futures
    assert "Анна" not in futures and "Вера" not in futures

    recents = client.get("/tutor/mailings/recipients?segment=recent", headers=HTMX).text
    assert "Вера" in recents
    # 8 дней назад — вне окна 7 дней.
    assert "Глеб" not in recents and "Даша" not in recents

    no_lessons = client.get(
        "/tutor/mailings/recipients?segment=no_lessons", headers=HTMX
    ).text
    # «Без уроков» = нет запланированных: никогда не занимался (Даша),
    # уроки прошли (Вера, Глеб) или есть только долг без уроков (Анна).
    assert (
        "Даша" in no_lessons
        and "Вера" in no_lessons
        and "Глеб" in no_lessons
        and "Анна" in no_lessons
    )
    assert "Борис" not in no_lessons


def test_recipients_show_balance_and_next_lesson(client, owner, student_factory, lesson_factory, operation_factory):
    debtor = student_factory(tutor_id=owner, first_name="Иван", last_name="Иванов")
    operation_factory(student_id=debtor, kind="lesson", amount=3300, status=None)
    lesson_factory(
        student_id=debtor,
        status="planned",
        starts_at=datetime.now(UTC) + timedelta(days=1),
    )

    markup = client.get("/tutor/mailings/recipients", headers=HTMX).text
    assert "Иван Иванов" in markup
    # Деньги выводит общий balance_label: типографский минус и неразрывные
    # пробелы — строку сравниваем тем же хелпером, а не литералом.
    assert balance_label(-3300) in markup
    assert "След. урок:" in markup
    assert "money-value--debt" in markup


def test_recipients_partial_root_is_self_replaceable(client, owner, student_factory):
    """Корень партиала несёт свой id — фильтры работают после любой перерисовки.

    Регрессия: `id="mailing-recipients"` жил на обёртке снаружи партиала,
    первая же подмена (outerHTML) съедала цель `hx-target` чипов и поиска —
    фильтр срабатывал один раз, а переключить/отменить его было нельзя.
    """
    student_factory(tutor_id=owner, first_name="Аня")
    for segment in ("", "debtors", "upcoming", "recent", "no_lessons"):
        response = client.get(
            f"/tutor/mailings/recipients?segment={segment}", headers=HTMX
        )
        assert response.status_code == 200
        assert 'id="mailing-recipients"' in response.text
        assert 'hx-target="#mailing-recipients"' in response.text


def test_composer_has_placeholder_token_buttons(client, owner):
    """Под полем текста — кнопки-облочки подстановок (вставка на курсор)."""
    markup = client.get("/tutor/mailings").text
    assert "mailing-tokens__btn" in markup
    for token in ("{имя}", "{баланс}", "{следующий_урок}"):
        assert f"insertToken('{token}')" in markup
        assert f">{token}</button>" in markup


def test_recipients_isolated_by_tutor(client, owner, tutor_factory, student_factory):
    other_tutor = tutor_factory()
    student_factory(tutor_id=other_tutor, first_name="Чужой", phone="+7 900 999-00-11")

    markup = client.get("/tutor/mailings/recipients", headers=HTMX).text
    assert "Чужой" not in markup


def test_recipients_channels_pills(client, owner, student_factory, invite_factory):
    bound = student_factory(tutor_id=owner, first_name="Связной")
    invite_factory(student_id=bound, messenger="telegram", chat_id="100200300")
    unbound = student_factory(tutor_id=owner, first_name="Молчун")

    markup = client.get("/tutor/mailings/recipients", headers=HTMX).text
    # Telegram подключён (акцентная метка), MAX нет; у «Молчуна» каналов нет —
    # чекбокс задизейблен.
    assert "mailing-channels__pill--on" in markup
    assert 'disabled title="Нет подключённых каналов"' in markup
    assert markup.count("disabled") >= 1
    assert "Связной" in markup and "Молчун" in markup


# ---------------------------------------------------------------------------
# Шаблоны сообщений
# ---------------------------------------------------------------------------


def test_template_create_via_http(client, owner):
    response = client.post(
        "/tutor/mailings/templates",
        data={"title": "Оплата", "text": "{имя}, баланс {баланс}"},
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.text == ""
    assert response.headers["HX-Trigger"] == "templates-saved"

    with SessionLocal() as db:
        template = db.scalars(select(MessageTemplate)).one()
    assert template.title == "Оплата"
    assert template.text == "{имя}, баланс {баланс}"


def test_template_create_validation(client, owner):
    response = client.post(
        "/tutor/mailings/templates",
        data={"title": "", "text": "текст"},
        headers=HTMX,
    )
    assert "Укажите название шаблона." in response.text
    assert 'id="mailings-template-form-dialog"' in response.text

    with SessionLocal() as db:
        assert db.scalars(select(MessageTemplate)).all() == []


def test_templates_dialog_lists_templates(client, owner, template_factory):
    template_factory(owner, title="Занятие", text="Скоро занятие!")
    template_factory(owner, title="Оплата", text="Ждём оплату")

    markup = client.get("/tutor/mailings/templates", headers=HTMX).text
    assert "Шаблоны сообщений" in markup
    assert "Занятие" in markup and "Скоро занятие!" in markup
    assert "Оплата" in markup
    assert f"/tutor/mailings/templates/{template_factory.__name__}" not in markup


def test_template_select_on_page(client, owner, template_factory):
    template_factory(owner, title="Занятие", text="Скоро занятие!")
    markup = client.get("/tutor/mailings").text
    assert 'data-text="Скоро занятие!"' in markup
    assert 'value=""' in markup  # плейсхолдер «Шаблон»


def test_template_new_dialog_carries_text(client, owner):
    response = client.get(
        "/tutor/mailings/templates/new", params={"text": "Скоро занятие!"}, headers=HTMX
    )
    assert "Сохранить как шаблон" in response.text
    assert "Скоро занятие!" in response.text


def test_template_update_and_delete(client, owner, template_factory):
    template_id = template_factory(owner, title="Старое", text="текст")

    updated = client.post(
        f"/tutor/mailings/templates/{template_id}",
        data={"title": "Новое", "text": "новый текст"},
        headers=HTMX,
    )
    assert updated.status_code == 200
    assert updated.headers["HX-Trigger"] == "templates-saved"
    with SessionLocal() as db:
        template = db.get(MessageTemplate, template_id)
    assert template.title == "Новое" and template.text == "новый текст"

    deleted = client.post(
        f"/tutor/mailings/templates/{template_id}/delete", headers=HTMX
    )
    assert deleted.status_code == 200
    assert deleted.headers["HX-Trigger"] == "templates-saved"
    assert "Шаблонов пока нет" in deleted.text
    with SessionLocal() as db:
        assert db.get(MessageTemplate, template_id) is None


def test_template_edit_dialog_prefills(client, owner, template_factory):
    template_id = template_factory(owner, title="Занятие", text="Скоро занятие!")
    response = client.get(f"/tutor/mailings/templates/{template_id}/edit", headers=HTMX)
    assert "Правка шаблона" in response.text
    assert 'value="Занятие"' in response.text
    assert "Скоро занятие!" in response.text


def test_template_actions_isolated_404(client, owner, tutor_factory, template_factory):
    other_tutor = tutor_factory()
    foreign_id = template_factory(other_tutor, title="Чужой", text="чужой текст")

    assert client.get(
        f"/tutor/mailings/templates/{foreign_id}/edit", headers=HTMX
    ).status_code == 404
    assert (
        client.post(
            f"/tutor/mailings/templates/{foreign_id}",
            data={"title": "x", "text": "y"},
            headers=HTMX,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/tutor/mailings/templates/{foreign_id}/delete", headers=HTMX
        ).status_code
        == 404
    )
    # Существование чужой записи не раскрывается и несуществующим id.
    assert (
        client.get(
            "/tutor/mailings/templates/00000000-0000-0000-0000-000000000000/edit",
            headers=HTMX,
        ).status_code
        == 404
    )


def test_template_actions_without_js_redirect(client, owner):
    created = client.post(
        "/tutor/mailings/templates",
        data={"title": "Шаблон", "text": "текст"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/tutor/mailings"


# ---------------------------------------------------------------------------
# Отправка рассылки
# ---------------------------------------------------------------------------


def test_send_flow_htmx(client, owner, student_factory, invite_factory, monkeypatch):
    student_id = student_factory(tutor_id=owner, first_name="Пётр")
    invite_factory(student_id=student_id, messenger="telegram", chat_id="100200300")
    _connect_tokens(owner)
    calls = []
    _patch_urlopen(monkeypatch, _ok_responder, calls)

    response = client.post(
        "/tutor/mailings/send",
        data={"student_ids": student_id, "text": "Привет, {имя}!"},
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "mailing-sent"
    # Композер после отправки: текст очищен, сводка показана.
    assert "Доставлено сообщений: 1" in response.text

    assert len(calls) == 1
    assert calls[0]["data"]["text"] == "Привет, Пётр!"
    assert calls[0]["data"]["chat_id"] == "100200300"

    records = _stored_sent()
    assert len(records) == 1
    assert records[0].status == "sent"
    assert records[0].student_id == student_id
    assert records[0].text == "Привет, Пётр!"


def test_send_substitutes_balance(client, owner, student_factory, invite_factory, operation_factory, monkeypatch):
    student_id = student_factory(tutor_id=owner, first_name="Пётр")
    invite_factory(student_id=student_id, messenger="telegram", chat_id="100200300")
    operation_factory(student_id=student_id, kind="lesson", amount=1200, status=None)
    _connect_tokens(owner)
    calls = []
    _patch_urlopen(monkeypatch, _ok_responder, calls)

    client.post(
        "/tutor/mailings/send",
        data={"student_ids": student_id, "text": "{имя}, долг {баланс}"},
        headers=HTMX,
    )
    assert calls[0]["data"]["text"] == f"Пётр, долг {balance_label(-1200)}"


def test_send_next_lesson_placeholder(client, owner, student_factory, invite_factory, lesson_factory, monkeypatch):
    student_id = student_factory(tutor_id=owner, first_name="Пётр")
    invite_factory(student_id=student_id, messenger="telegram", chat_id="100200300")
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2030, 5, 20, 14, 0, tzinfo=UTC),
    )
    _connect_tokens(owner)
    calls = []
    _patch_urlopen(monkeypatch, _ok_responder, calls)

    client.post(
        "/tutor/mailings/send",
        data={"student_ids": student_id, "text": "Урок: {следующий_урок}"},
        headers=HTMX,
    )
    assert calls[0]["data"]["text"] == "Урок: 20 мая в 14:00"


def test_send_to_both_channels(client, owner, student_factory, invite_factory, monkeypatch):
    student_id = student_factory(tutor_id=owner, first_name="Пётр")
    invite_factory(student_id=student_id, messenger="telegram", chat_id="100200300")
    invite_factory(student_id=student_id, messenger="max", chat_id="555000111")
    _connect_tokens(owner, messengers=("telegram", "max"))
    calls = []
    _patch_urlopen(monkeypatch, _ok_responder, calls)

    response = client.post(
        "/tutor/mailings/send",
        data={"student_ids": student_id, "text": "всем"},
        headers=HTMX,
    )
    assert len(calls) == 2
    assert "Доставлено сообщений: 2" in response.text
    # Telegram — chat_id в теле, MAX — в query (контракты Bot API).
    by_host = {("api.telegram.org" in call["url"]): call for call in calls}
    assert by_host[True]["data"]["chat_id"] == "100200300"
    assert "chat_id=555000111" in by_host[False]["url"]


def test_send_error_logged_and_shown(client, owner, student_factory, invite_factory, monkeypatch):
    student_id = student_factory(tutor_id=owner, first_name="Пётр")
    invite_factory(student_id=student_id, messenger="telegram", chat_id="100200300")
    _connect_tokens(owner)
    calls = []
    _patch_urlopen(monkeypatch, _error_responder, calls)

    response = client.post(
        "/tutor/mailings/send",
        data={"student_ids": student_id, "text": "не ушло"},
        headers=HTMX,
    )
    # Доставок нет — текст остаётся в поле, событие сброса не шлётся.
    assert "HX-Trigger" not in response.headers
    assert "не ушло" in response.text
    assert "chat not found" in response.text

    records = _stored_sent()
    assert len(records) == 1
    assert records[0].status == "error"
    assert "chat not found" in records[0].error
    assert records[0].student_id == student_id


def test_send_skips_students_without_channels(client, owner, student_factory, monkeypatch):
    student_id = student_factory(tutor_id=owner, first_name="Молчун")
    _connect_tokens(owner)

    def fail(*args, **kwargs):
        raise AssertionError("сеть не должна вызываться")

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    response = client.post(
        "/tutor/mailings/send",
        data={"student_ids": student_id, "text": "текст"},
        headers=HTMX,
    )
    assert "пропущено без каналов: 1" in response.text
    assert _stored_sent() == []


def test_send_ignores_foreign_student_ids(
    client, owner, tutor_factory, student_factory, monkeypatch
):
    other_tutor = tutor_factory()
    foreign_id = student_factory(tutor_id=other_tutor, first_name="Чужой")
    _connect_tokens(owner)

    def fail(*args, **kwargs):
        raise AssertionError("сеть не должна вызываться")

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    response = client.post(
        "/tutor/mailings/send",
        data={"student_ids": foreign_id, "text": "текст"},
        headers=HTMX,
    )
    assert "Выберите хотя бы одного ученика." in response.text
    assert _stored_sent() == []


def test_send_requires_text(client, owner, student_factory, invite_factory, monkeypatch):
    student_id = student_factory(tutor_id=owner, first_name="Пётр")
    invite_factory(student_id=student_id, messenger="telegram", chat_id="100200300")
    _connect_tokens(owner)

    def fail(*args, **kwargs):
        raise AssertionError("сеть не должна вызываться")

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    response = client.post(
        "/tutor/mailings/send",
        data={"student_ids": student_id, "text": "   "},
        headers=HTMX,
    )
    assert "Введите текст сообщения." in response.text
    assert _stored_sent() == []


def test_send_without_js_redirects(client, owner, student_factory, invite_factory, monkeypatch):
    student_id = student_factory(tutor_id=owner, first_name="Пётр")
    invite_factory(student_id=student_id, messenger="telegram", chat_id="100200300")
    _connect_tokens(owner)
    calls = []
    _patch_urlopen(monkeypatch, _ok_responder, calls)

    response = client.post(
        "/tutor/mailings/send",
        data={"student_ids": student_id, "text": "без JS"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/mailings"
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Журнал (вкладка «История»)
# ---------------------------------------------------------------------------


def test_history_shows_entries(client, owner, student_factory, invite_factory, monkeypatch):
    student_id = student_factory(tutor_id=owner, first_name="Пётр")
    invite_factory(student_id=student_id, messenger="telegram", chat_id="100200300")
    _connect_tokens(owner)
    calls = []
    _patch_urlopen(monkeypatch, _ok_responder, calls)
    client.post(
        "/tutor/mailings/send",
        data={"student_ids": student_id, "text": "Привет!"},
        headers=HTMX,
    )

    markup = client.get("/tutor/mailings?tab=history").text
    assert "Пётр" in markup
    assert "Telegram" in markup
    assert "Доставлено" in markup
    assert "Привет!" in markup


def test_history_isolated_by_tutor(client, owner, tutor_factory, monkeypatch):
    """Записи чужого репетитора не видны, даже отправленные его ботом."""
    from app.messenger.services.send import send_message

    other_tutor = tutor_factory()
    with SessionLocal() as db:
        set_param(db, other_tutor, token_key("telegram"), TELEGRAM_TOKEN)
        calls = []
        _patch_urlopen(monkeypatch, _ok_responder, calls)
        send_message(db, other_tutor, "telegram", "777888", "чужое сообщение")
        db.commit()

    markup = client.get("/tutor/mailings?tab=history").text
    assert "чужое сообщение" not in markup
    assert "Сообщений пока нет" in markup


def test_send_message_logs_unknown_chat_without_student(client, owner, monkeypatch):
    """Чат вне привязок пишется в журнал без ученика (например, канал репетитора)."""
    from app.messenger.services.send import send_message

    _connect_tokens(owner)
    calls = []
    _patch_urlopen(monkeypatch, _ok_responder, calls)
    with SessionLocal() as db:
        errors = send_message(db, owner, "telegram", "777888", "привет каналу")
        db.commit()

    assert errors == []
    records = _stored_sent()
    assert len(records) == 1
    assert records[0].student_id is None
    assert records[0].recipient == "777888"


def test_validation_errors_are_not_logged(client, owner, monkeypatch):
    """Ошибки до попытки доставки (не подключён) журнал не пишут."""
    from app.messenger.services.send import send_message

    def fail(*args, **kwargs):
        raise AssertionError("сеть не должна вызываться")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with SessionLocal() as db:
        send_message(db, owner, "telegram", "100200300", "привет")
        db.commit()

    assert _stored_sent() == []
