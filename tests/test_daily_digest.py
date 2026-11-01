"""Дневная сводка уроков в мессенджеры (задание cron `messenger.daily_digest`).

Задание вызывается так, как его запускает runner: своя сессия `SessionLocal`
и коммит. HTTP-транспорт подменяется (monkeypatch на
`urllib.request.urlopen`): сеть в тестах не дёргается, но путь вызова —
тот же, что в бою.

Время проверок фиксировано аргументом `now` (aware UTC), уроки создаются на
ту же календарную дату: тест не зависит от даты прогона.
"""

import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime

from app.common.services import cron as cron_module
from app.database import SessionLocal
from app.messenger.services.binding import chat_id_key
from app.messenger.services.daily_digest import DIGEST_SENT_KEY, run_daily_digests
from app.messenger.services.messengers import token_key
from app.tutor.models.tutor_settings import TutorSettings
from app.tutor.services.params import get_param, set_param

TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
MAX_TOKEN = "pKcfaXfFUnfTSMPSYJjpdHHnPEMucRQGxFYEXhIq"
CHAT_ID = "100200300"
MAX_CHAT_ID = "700800900"

# Полдень «дня сводки»: время урока и момент проверки в одном дне.
DAY = datetime(2026, 11, 2, tzinfo=UTC)
NOON = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
LESSON_AT = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Вспомогательное: транспорт, настройки, прогон задания
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
    так проверяется изоляция каналов (сбой одного не мешает другому).
    """

    def fake_urlopen(request, timeout=None, context=None):
        url = request.full_url
        call = {
            "url": url,
            "data": json.loads(request.data.decode()),
        }
        calls.append(call)
        if fail_messenger == "telegram" and "api.telegram.org" in url:
            raise urllib.error.HTTPError(
                url, 400, "Bad Request", None,
                io.BytesIO(b'{"ok": false, "description": "chat not found"}'),
            )
        if fail_messenger == "max" and "max.ru" in url:
            raise urllib.error.HTTPError(
                url, 404, "Not Found", None,
                io.BytesIO('{"code": "chat.not.found", "message": "Чат не найден"}'.encode()),
            )
        if "api.telegram.org" in url:
            return _FakeResponse({"ok": True, "result": {"message_id": 1}})
        return _FakeResponse({"message": {"body": {"text": call["data"]["text"]}}})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _connect(db, tutor_id, messenger, chat_id):
    """Подключает канал: токен бота + привязанный чат."""
    token = TOKEN if messenger == "telegram" else MAX_TOKEN
    set_param(db, tutor_id, token_key(messenger), token)
    set_param(db, tutor_id, chat_id_key(messenger), chat_id)


def _settings(tutor_id, **values):
    """Создаёт строку настроек репетитора с нужными полями."""
    from app.tutor.models.tutor_settings import default_values

    payload = default_values()
    payload.update(values)
    with SessionLocal() as db:
        db.add(TutorSettings(tutor_id=tutor_id, **payload))
        db.commit()


def _run(now=NOON) -> int:
    """Прогон задания как у runner'а: сессия + коммит."""
    with SessionLocal() as db:
        sent = run_daily_digests(db, now=now)
        db.commit()
    return sent


def _texts(calls):
    """Тексты отправленных сообщений."""
    return [call["data"]["text"] for call in calls]


# ---------------------------------------------------------------------------
# Реестр cron
# ---------------------------------------------------------------------------

def test_registry_contains_daily_digest():
    """В реестре заданий cron зарегистрирована дневная сводка."""
    names = [name for name, _ in cron_module.TASKS]
    assert "messenger.daily_digest" in names


# ---------------------------------------------------------------------------
# Условие отправки
# ---------------------------------------------------------------------------

def test_sends_after_digest_time_to_all_channels(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """После времени сводки сообщение уходит во все привязанные каналы."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Петров")
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT, price=1200)

    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)
        _connect(db, tutor_id, "max", MAX_CHAT_ID)

    assert _run() == 1

    assert len(calls) == 2
    telegram = next(call for call in calls if "api.telegram.org" in call["url"])
    assert telegram["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert telegram["data"]["chat_id"] == CHAT_ID
    max_call = next(call for call in calls if "max.ru" in call["url"])
    assert max_call["url"] == f"https://platform-api2.max.ru/messages?chat_id={MAX_CHAT_ID}"

    text = telegram["data"]["text"]
    assert "Сводка уроков на 02.11.2026" in text
    assert "12:00 — Иван Петров" in text
    # Оба канала получили одинаковый текст.
    assert _texts(calls) == [text, text]

    with SessionLocal() as db:
        assert get_param(db, tutor_id, DIGEST_SENT_KEY) == "2026-11-02"


def test_silent_before_digest_time(monkeypatch, tutor_factory, student_factory, lesson_factory):
    """До времени из профиля сводка не отправляется и день не помечается."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    # 09:00 UTC при времени сводки 09:00 — ещё рано (сравнение «не раньше»).
    assert _run(now=datetime(2026, 11, 2, 8, 59, tzinfo=UTC)) == 0

    assert calls == []
    with SessionLocal() as db:
        assert get_param(db, tutor_id, DIGEST_SENT_KEY) is None


def test_second_run_same_day_is_silent(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Повторный прогон в тот же день ничего не отправляет."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1
    assert len(calls) == 1

    assert _run(now=datetime(2026, 11, 2, 23, 0, tzinfo=UTC)) == 0
    assert len(calls) == 1


def test_next_day_sends_again(monkeypatch, tutor_factory, student_factory, lesson_factory):
    """На следующий день сводка отправляется снова."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2026, 11, 3, 12, 0, tzinfo=UTC),
    )
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1
    assert _run(now=datetime(2026, 11, 3, 10, 0, tzinfo=UTC)) == 1

    assert len(calls) == 2
    assert "Сводка уроков на 03.11.2026" in _texts(calls)[1]


def test_disabled_digest_is_silent(monkeypatch, tutor_factory, student_factory, lesson_factory):
    """Флаг «Дневная сводка» выключен — сообщений нет."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)
    _settings(tutor_id, notify_daily_digest=False)

    assert _run() == 0
    assert calls == []


def test_custom_digest_time_is_respected(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Время отправки берётся из профиля, а не из дефолта."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)
    _settings(tutor_id, digest_time="18:00")

    assert _run() == 0
    assert _run(now=datetime(2026, 11, 2, 18, 0, tzinfo=UTC)) == 1


# ---------------------------------------------------------------------------
# Содержание сводки
# ---------------------------------------------------------------------------

def test_group_lesson_shows_group_name(
    monkeypatch, tutor_factory, group_factory, group_member_factory, student_factory,
    lesson_factory,
):
    """Групповой урок подписан именем группы, участники — по цене группы."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    group_id = group_factory(tutor_id=tutor_id, name="Математика 7Б", price_per_lesson=1000)
    first = student_factory(tutor_id=tutor_id, first_name="Анна")
    second = student_factory(tutor_id=tutor_id, first_name="Борис")
    group_member_factory(group_id=group_id, student_id=first)
    # Индивидуальная цена участника переопределяет цену группы.
    group_member_factory(group_id=group_id, student_id=second, price_override=1500)
    lesson_factory(group_id=group_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1

    text = _texts(calls)[0]
    assert "12:00 — Группа: Математика 7Б" in text
    # Балансы нулевые: не хватает полной цены урока у каждого участника.
    assert "Анна: не хватает 1\u00a0000\u00a0₽ (на счету 0\u00a0₽, урок 1\u00a0000\u00a0₽)" in text
    assert "Борис: не хватает 1\u00a0500\u00a0₽ (на счету 0\u00a0₽, урок 1\u00a0500\u00a0₽)" in text


def test_shortfall_note_when_balance_is_low(
    monkeypatch, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """Баланс меньше цены урока — в строке появляется пометка о нехватке."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван")
    operation_factory(student_id=student_id, kind="payment", amount=500)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT, price=1200)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1

    text = _texts(calls)[0]
    assert "не хватает 700\u00a0₽" in text
    assert "на счету 500\u00a0₽" in text
    assert "урок 1\u00a0200\u00a0₽" in text


def test_no_shortfall_note_when_balance_is_enough(
    monkeypatch, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """Денег хватает — пометки нет, строка остаётся только временем и именем."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван")
    operation_factory(student_id=student_id, kind="payment", amount=5000)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT, price=1200)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1

    text = _texts(calls)[0]
    assert "12:00 — Иван" in text
    assert "не хватает" not in text


def test_shortfall_note_can_be_disabled(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Флаг «Не хватает средств» выключен — сводка без пометок."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван")
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT, price=1200)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)
    _settings(tutor_id, notify_insufficient_funds=False)

    assert _run() == 1

    text = _texts(calls)[0]
    assert "12:00 — Иван" in text
    assert "не хватает" not in text


def test_completed_lessons_are_not_in_digest(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Сводка — план дня: проведённые уроки в неё не попадают."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT, price=1200)
    lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=datetime(2026, 11, 2, 15, 0, tzinfo=UTC),
        price=1200,
    )
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1

    text = _texts(calls)[0]
    assert "12:00" in text
    assert "15:00" not in text


# ---------------------------------------------------------------------------
# Края и изоляция
# ---------------------------------------------------------------------------

def test_no_lessons_no_message(monkeypatch, tutor_factory):
    """Уроков на день нет — сообщения нет, но день помечен обработанным."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 0
    assert calls == []
    with SessionLocal() as db:
        assert get_param(db, tutor_id, DIGEST_SENT_KEY) == "2026-11-02"


def test_tutor_without_channels_is_skipped(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Нет привязанных чатов — сеть не дёргается вовсе."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)

    assert _run() == 0
    assert calls == []


def test_other_tutor_lessons_are_isolated(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Чужие уроки в сводку не попадают."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    other_id = tutor_factory()
    own = student_factory(tutor_id=tutor_id, first_name="Свой")
    alien = student_factory(tutor_id=other_id, first_name="Чужой")
    lesson_factory(student_id=own, status="planned", starts_at=LESSON_AT)
    lesson_factory(student_id=alien, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1

    text = _texts(calls)[0]
    assert "Свой" in text
    assert "Чужой" not in text


def test_timezone_shifts_send_moment(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Время сводки — настенное время педагога, а не UTC."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory(timezone="Asia/Tokyo")
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=datetime(2026, 11, 2, 1, 0, tzinfo=UTC),
    )
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    # 00:30 UTC — это 09:30 в Токио: время сводки 09:00 уже наступило.
    assert _run(now=datetime(2026, 11, 2, 0, 30, tzinfo=UTC)) == 1

    # Урок 01:00 UTC показан настенным временем Токио.
    assert "10:00 — " in _texts(calls)[0]


def test_one_channel_failure_does_not_block_another(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Ошибка Telegram не мешает доставке в MAX; маркер дня всё равно ставится."""
    calls = []
    _patch_urlopen(monkeypatch, calls, fail_messenger="telegram")
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(student_id=student_id, status="planned", starts_at=LESSON_AT)
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)
        _connect(db, tutor_id, "max", MAX_CHAT_ID)

    # Сводка не доставлена в Telegram, но ушла в MAX: считаем отправленной.
    assert _run() == 1

    urls = [call["url"] for call in calls]
    assert any("api.telegram.org" in url for url in urls)
    assert any("max.ru" in url for url in urls)
    with SessionLocal() as db:
        assert get_param(db, tutor_id, DIGEST_SENT_KEY) == "2026-11-02"


def test_long_digest_is_truncated(
    monkeypatch, tutor_factory, student_factory, lesson_factory
):
    """Длинный день обрезается под лимит сообщения Telegram."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    for minute in range(0, 60):
        student_id = student_factory(
            tutor_id=tutor_id,
            first_name="Оченьдлинноеимяученика" * 3,
            last_name=str(minute),
        )
        lesson_factory(
            student_id=student_id,
            status="planned",
            starts_at=datetime(2026, 11, 2, 12, minute % 60, tzinfo=UTC),
            price=1200,
        )
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1

    text = _texts(calls)[0]
    assert len(text) <= 4000
    assert text.endswith("…")
