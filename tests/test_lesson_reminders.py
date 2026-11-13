"""Напоминания о начале урока (задание cron `messenger.lesson_reminders`).

Задание вызывается так, как его запускает runner: своя сессия
`SessionLocal` и коммит. HTTP-транспорт подменяется (monkeypatch на
`urllib.request.urlopen`): сеть в тестах не дёргается, но путь вызова —
тот же, что в бою.

Время проверок фиксировано аргументом `now` (aware UTC), уроки создаются
относительно него: тест не зависит от даты прогона.
"""

import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.common.services import cron as cron_module
from app.database import SessionLocal
from app.lesson.models.lesson_reminder import LessonReminder
from app.messenger.models.student_invite import StudentMessengerInvite
from app.messenger.services.binding import chat_id_key
from app.messenger.services.lesson_reminders import run_lesson_reminders
from app.messenger.services.messengers import token_key
from app.tutor.models.tutor_settings import TutorSettings
from app.tutor.services.params import set_param

TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
MAX_TOKEN = "pKcfaXfFUnfTSMPSYJjpdHHnPEMucRQGxFYEXhIq"
CHAT_ID = "100200300"
MAX_CHAT_ID = "700800900"
STUDENT_CHAT_ID = "400500600"

# Момент проверки и урок через час: текст совпадает с примером постановки.
NOW = datetime(2026, 11, 13, 8, 30, tzinfo=UTC)
LESSON_AT = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Вспомогательное: транспорт, настройки, привязки, прогон задания
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


def _patch_urlopen(monkeypatch, calls, *, fail_messenger=None):
    """Подменяет urlopen; каждый вызов дописывается в `calls`.

    `fail_messenger` — имя мессенджера, для которого API отвечает ошибкой:
    так проверяется изоляция каналов.
    """

    def fake_urlopen(request, timeout=None, context=None):
        url = request.full_url
        call = {"url": url, "data": json.loads(request.data.decode())}
        calls.append(call)
        if fail_messenger == "telegram" and "api.telegram.org" in url:
            raise urllib.error.HTTPError(
                url, 400, "Bad Request", None,
                io.BytesIO(b'{"ok": false, "description": "chat not found"}'),
            )
        if "api.telegram.org" in url:
            return _FakeResponse({"ok": True, "result": {"message_id": 1}})
        return _FakeResponse({"message": {"body": {"text": call["data"]["text"]}}})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _connect_tutor(db, tutor_id, messenger, chat_id):
    """Подключает канал репетитора: токен бота + привязанный чат."""
    token = TOKEN if messenger == "telegram" else MAX_TOKEN
    set_param(db, tutor_id, token_key(messenger), token)
    set_param(db, tutor_id, chat_id_key(messenger), chat_id)


def _connect_student(db, tutor_id, student_id, messenger, chat_id):
    """Подключает канал ученика: приглашение с привязанным chat_id."""
    messenger_token = TOKEN if messenger == "telegram" else MAX_TOKEN
    set_param(db, tutor_id, token_key(messenger), messenger_token)
    db.add(
        StudentMessengerInvite(
            tutor_id=tutor_id,
            student_id=student_id,
            messenger=messenger,
            chat_id=chat_id,
            chat_label=chat_id,
        )
    )
    db.commit()


def _settings(tutor_id, **values):
    """Создаёт строку настроек репетитора с нужными полями."""
    from app.tutor.models.tutor_settings import default_values

    payload = default_values()
    payload.update(values)
    with SessionLocal() as db:
        db.add(TutorSettings(tutor_id=tutor_id, **payload))
        db.commit()


def _run(now=NOW) -> int:
    """Прогон задания как у runner'а: сессия + коммит."""
    with SessionLocal() as db:
        sent = run_lesson_reminders(db, now=now)
        db.commit()
    return sent


def _texts(calls):
    """Тексты отправленных сообщений."""
    return [call["data"]["text"] for call in calls]


def _markers():
    """Маркеры отправки напоминаний."""
    with SessionLocal() as db:
        return db.scalars(select(LessonReminder)).all()


# ---------------------------------------------------------------------------
# Реестр cron
# ---------------------------------------------------------------------------


def test_registry_contains_lesson_reminders():
    """В реестре заданий cron зарегистрированы напоминания об уроке."""
    names = [name for name, _ in cron_module.TASKS]
    assert "messenger.lesson_reminders" in names


# ---------------------------------------------------------------------------
# Интервалы и текст репетитору
# ---------------------------------------------------------------------------


def test_sends_hour_reminder_to_all_tutor_channels(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """За час до урока сообщение уходит во все каналы репетитора."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Иванов")
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)
        _connect_tutor(db, tutor_id, "max", MAX_CHAT_ID)

    assert _run() == 2

    expected = "Через 1 час урок с Иван Иванов — \nВремя: 13 ноября в 09:30"
    assert _texts(calls) == [expected, expected]
    assert len(_markers()) == 1


def test_fifteen_minutes_reminder_text(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Интервал 15 минут формулируется «Через 15 минут»."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Иванов")
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=NOW + timedelta(minutes=15),
    )
    _settings(tutor_id, reminder_offsets=[15])
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1
    assert _texts(calls)[0].startswith("Через 15 минут урок с Иван Иванов — \n")


def test_day_reminder_text(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Интервал 24 часа формулируется «Завтра»."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Иванов")
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=NOW + timedelta(hours=24),
    )
    _settings(tutor_id, reminder_offsets=[1440])
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1
    text = _texts(calls)[0]
    assert text.startswith("Завтра урок с Иван Иванов — \n")
    assert "Время: 14 ноября в 08:30" in text


def test_disabled_switch_is_silent(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Переключатель «Напоминание об уроке» выключен — сообщений нет."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    _settings(tutor_id, notify_lesson_reminder=False, reminder_offsets=[60])
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 0
    assert calls == []
    assert _markers() == []


def test_disabled_offset_is_silent(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Интервал не включён — напоминание за него не отправляется."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    _settings(tutor_id, reminder_offsets=[15])
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 0
    assert calls == []


# ---------------------------------------------------------------------------
# Ученик
# ---------------------------------------------------------------------------


def test_student_gets_message_without_name(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """При включённом напоминании ученик получает текст без своего имени."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(
        tutor_id=tutor_id, first_name="Иван", last_name="Иванов", remind_lesson=True
    )
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)
        _connect_student(db, tutor_id, student_id, "telegram", STUDENT_CHAT_ID)

    assert _run() == 2

    expected = "Через 1 час урок — \nВремя: 13 ноября в 09:30"
    student_calls = [
        call for call in calls if call["data"].get("chat_id") == STUDENT_CHAT_ID
    ]
    assert [call["data"]["text"] for call in student_calls] == [expected]
    assert "Иван Иванов" not in student_calls[0]["data"]["text"]
    # Маркеры: один репетитору, один ученику.
    assert len(_markers()) == 2


def test_student_reminders_can_be_disabled(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """У ученика напоминания выключены — сообщение получает только репетитор."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, remind_lesson=False)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)
        _connect_student(db, tutor_id, student_id, "telegram", STUDENT_CHAT_ID)

    assert _run() == 1
    assert len(calls) == 1


def test_student_without_channels_gets_nothing(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Ни один канал ученика не подключён — отправки нет, маркера тоже."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, remind_lesson=True)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1
    assert [marker.audience for marker in _markers()] == ["tutor"]


def test_student_receives_in_own_timezone(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Время ученику показывается в его часовом поясе."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory(timezone="Europe/Moscow")
    student_id = student_factory(
        tutor_id=tutor_id,
        first_name="Иван",
        last_name="Иванов",
        remind_lesson=True,
        timezone="Asia/Tokyo",
    )
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)
        _connect_student(db, tutor_id, student_id, "telegram", STUDENT_CHAT_ID)

    assert _run() == 2

    tutor_text = next(
        call["data"]["text"]
        for call in calls
        if call["data"].get("chat_id") == CHAT_ID
    )
    student_text = next(
        call["data"]["text"]
        for call in calls
        if call["data"].get("chat_id") == STUDENT_CHAT_ID
    )
    # 09:30 UTC — 12:30 в Москве и 18:30 в Токио.
    assert "Время: 13 ноября в 12:30" in tutor_text
    assert "Время: 13 ноября в 18:30" in student_text


# ---------------------------------------------------------------------------
# Групповой урок
# ---------------------------------------------------------------------------


def test_group_lesson_uses_group_name(
    monkeypatch, tutor_factory, group_factory, group_member_factory, student_factory,
    lesson_factory,
):
    """В тексте репетитору вместо имени ученика — название группы."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    group_id = group_factory(tutor_id=tutor_id, name="Математика 7Б")
    student_id = student_factory(
        tutor_id=tutor_id, first_name="Анна", last_name="Петрова", remind_lesson=True
    )
    group_member_factory(group_id=group_id, student_id=student_id)
    lesson_factory(group_id=group_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)
        _connect_student(db, tutor_id, student_id, "telegram", STUDENT_CHAT_ID)

    assert _run() == 2

    tutor_text = next(
        call["data"]["text"]
        for call in calls
        if call["data"].get("chat_id") == CHAT_ID
    )
    student_text = next(
        call["data"]["text"]
        for call in calls
        if call["data"].get("chat_id") == STUDENT_CHAT_ID
    )
    assert tutor_text.startswith("Через 1 час урок с группой Математика 7Б — \n")
    assert "Анна" not in tutor_text
    assert student_text == "Через 1 час урок — \nВремя: 13 ноября в 09:30"


# ---------------------------------------------------------------------------
# Идемпотентность, пропущенный тик, отменённый урок
# ---------------------------------------------------------------------------


def test_second_run_does_not_duplicate(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Повторный прогон не отправляет уже отправленное напоминание."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, remind_lesson=True)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)
        _connect_student(db, tutor_id, student_id, "telegram", STUDENT_CHAT_ID)

    assert _run() == 2
    assert _run(now=NOW + timedelta(minutes=1)) == 0
    assert len(calls) == 2


def test_missed_tick_sends_next_run_with_same_text(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Пропущенный целевой тик догоняется следующим прогоном, текст не меняется."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Иванов")
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)

    # Целевой момент был в 08:30, cron сработал в 09:10 (до начала урока).
    assert _run(now=datetime(2026, 11, 13, 9, 10, tzinfo=UTC)) == 1
    assert _texts(calls) == [
        "Через 1 час урок с Иван Иванов — \nВремя: 13 ноября в 09:30"
    ]


def test_cancelled_lesson_is_silent(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Отменённый урок напоминания не получает."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, remind_lesson=True)
    lesson_factory(student_id=student_id, status="cancelled", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)
        _connect_student(db, tutor_id, student_id, "telegram", STUDENT_CHAT_ID)

    assert _run() == 0
    assert calls == []


def test_lesson_after_start_is_not_reminded(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """После начала урока догонять нечего."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)

    assert _run(now=LESSON_AT) == 0
    assert calls == []


# ---------------------------------------------------------------------------
# Изоляция и сбои каналов
# ---------------------------------------------------------------------------


def test_foreign_tutor_lessons_are_not_reminded(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Уроки и ученики чужого репетитора в выборку не попадают."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    owner_id = tutor_factory()
    student_id = student_factory(tutor_id=owner_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)

    stranger_id = tutor_factory()
    stranger_student = student_factory(tutor_id=stranger_id, remind_lesson=True)
    with SessionLocal() as db:
        _connect_tutor(db, stranger_id, "telegram", CHAT_ID)
        _connect_student(db, stranger_id, stranger_student, "telegram", STUDENT_CHAT_ID)

    assert _run() == 0
    assert calls == []


def test_group_member_from_other_tutor_is_skipped(
    monkeypatch, tutor_factory, group_factory, group_member_factory, student_factory,
    lesson_factory,
):
    """Чужой ученик в составе группы не получает напоминание."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    group_id = group_factory(tutor_id=tutor_id, name="Математика 7Б")
    foreign_student = student_factory(
        first_name="Чужой", remind_lesson=True, timezone="UTC"
    )
    group_member_factory(group_id=group_id, student_id=foreign_student)
    lesson_factory(group_id=group_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)
        _connect_student(db, tutor_id, foreign_student, "telegram", STUDENT_CHAT_ID)

    assert _run() == 1
    assert len(calls) == 1


def test_failed_channel_does_not_block_other(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Сбой Telegram не мешает доставке в MAX; маркер всё равно ставится."""
    calls = []
    _patch_urlopen(monkeypatch, calls, fail_messenger="telegram")
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect_tutor(db, tutor_id, "telegram", CHAT_ID)
        _connect_tutor(db, tutor_id, "max", MAX_CHAT_ID)

    assert _run() == 1
    # Telegram повторяется ретраем, MAX доставлен с первой попытки.
    max_calls = [call for call in calls if "max.ru" in call["url"]]
    assert len(max_calls) == 1
    assert len(_markers()) == 1