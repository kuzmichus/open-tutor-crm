"""Рассылка «День рождения» (задание cron `messenger.birthday_digest`).

Задание вызывается так, как его запускает runner: своя сессия `SessionLocal`
и коммит. HTTP-транспорт подменяется (monkeypatch на
`urllib.request.urlopen`): сеть в тестах не дёргается, но путь вызова —
тот же, что в бою.

Время проверок фиксировано аргументом `now` (aware UTC), даты рождения
создаются от той же календарной даты: тест не зависит от даты прогона.
"""

import io
import json
import urllib.error
import urllib.request
from datetime import UTC, date, datetime

from app.common.services import cron as cron_module
from app.database import SessionLocal
from app.messenger.services.binding import chat_id_key
from app.messenger.services.birthday_digest import (
    BIRTHDAY_SENT_KEY,
    birthday_message,
    notify_birthday_digest,
)
from app.messenger.services.messengers import token_key
from app.student.services.birthdays import age_on, birthday_students
from app.student.services.presentation import birthday_age_label
from app.tutor.models.tutor_settings import TutorSettings
from app.tutor.services.params import get_param, set_param

TOKEN = "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
MAX_TOKEN = "pKcfaXfFUnfTSMPSYJjpdHHnPEMucRQGxFYEXhIq"
CHAT_ID = "100200300"
MAX_CHAT_ID = "700800900"

# День рассылки и момент после времени отправки (09:00 по UTC-зоне).
DAY = date(2026, 11, 2)
NOON = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)

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
    так проверяется изоляция каналов и устойчивость задания к сбою.
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
        sent = notify_birthday_digest(db, now=now)
        db.commit()
    return sent

def _texts(calls):
    """Тексты отправленных сообщений."""
    return [call["data"]["text"] for call in calls]

# ---------------------------------------------------------------------------
# Реестр cron
# ---------------------------------------------------------------------------

def test_registry_contains_birthday_digest():
    """В реестре заданий cron зарегистрирована рассылка дней рождения."""
    names = [name for name, _ in cron_module.TASKS]
    assert "messenger.birthday_digest" in names

# ---------------------------------------------------------------------------
# Выборка именинников
# ---------------------------------------------------------------------------

def test_birthday_students_selection(tutor_factory, student_factory):
    """Попадает свой именинник; чужие, без даты и архивные — нет."""
    tutor_id = tutor_factory()
    other_tutor_id = tutor_factory()
    mine = student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    student_factory(tutor_id=other_tutor_id, birth_date=date(2014, 11, 2))
    student_factory(tutor_id=tutor_id, birth_date=None)
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2), status="archived")
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 3))

    with SessionLocal() as db:
        found = birthday_students(db, tutor_id, DAY)
        with_archived = birthday_students(db, tutor_id, DAY, include_archived=True)

    assert [student.id for student in found] == [mine]
    assert len(with_archived) == 2

def test_birthday_students_include_adults(tutor_factory, student_factory):
    """Взрослый ученик с днём рождения сегодня попадает в выборку."""
    tutor_id = tutor_factory()
    adult = student_factory(
        tutor_id=tutor_id, kind="adult", birth_date=date(1990, 11, 2)
    )

    with SessionLocal() as db:
        found = birthday_students(db, tutor_id, DAY)

    assert [student.id for student in found] == [adult]

def test_birthday_students_sorted_by_last_name(tutor_factory, student_factory):
    """Порядок — по фамилии; ученик без фамилии встаёт по имени."""
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, first_name="Яков", last_name="Яковлев",
                    birth_date=date(2010, 11, 2))
    student_factory(tutor_id=tutor_id, first_name="Анна", last_name="Абрамова",
                    birth_date=date(2012, 11, 2))
    student_factory(tutor_id=tutor_id, first_name="Борис", last_name=None,
                    birth_date=date(2011, 11, 2))

    with SessionLocal() as db:
        found = birthday_students(db, tutor_id, DAY)

    assert [student.first_name for student in found] == ["Анна", "Борис", "Яков"]

def test_leap_day_is_not_sent_in_common_year(tutor_factory, student_factory):
    """29 февраля в невисокосный год в рассылку не попадает."""
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2016, 2, 29))

    with SessionLocal() as db:
        assert birthday_students(db, tutor_id, date(2027, 2, 28)) == []
        assert birthday_students(db, tutor_id, date(2027, 3, 1)) == []
        assert len(birthday_students(db, tutor_id, date(2028, 2, 29))) == 1

# ---------------------------------------------------------------------------
# Подписи: возраст
# ---------------------------------------------------------------------------

def test_age_on_and_plural():
    """Возраст считается от даты рождения, подпись склоняется по-русски."""
    born = date(2014, 11, 2)
    assert age_on(born, DAY) == 12
    assert age_on(date(2027, 1, 1), DAY) is None  # год рождения в будущем
    assert birthday_age_label(born, DAY) == "12 лет"
    assert birthday_age_label(date(2025, 11, 2), DAY) == "1 год"
    assert birthday_age_label(date(2024, 11, 2), DAY) == "2 года"
    assert birthday_age_label(date(2021, 11, 2), DAY) == "5 лет"
    assert birthday_age_label(date(2015, 11, 2), DAY) == "11 лет"
    assert birthday_age_label(date(2005, 11, 2), DAY) == "21 год"
    assert birthday_age_label(None, DAY) == ""
    assert birthday_age_label(date(2027, 1, 1), DAY) == ""

def test_message_text(tutor_factory, student_factory):
    """Текст сообщения: заголовок с датой и строки «• Имя Фамилия — N лет»."""
    tutor_id = tutor_factory()
    student_factory(
        tutor_id=tutor_id, first_name="Иван", last_name="Иванов",
        birth_date=date(2014, 11, 2),
    )
    student_factory(
        tutor_id=tutor_id, first_name="Пётр", last_name="Петров",
        birth_date=date(2025, 11, 2),
    )

    with SessionLocal() as db:
        rows = birthday_students(db, tutor_id, DAY)

    text = birthday_message(rows, DAY)
    assert text.splitlines()[0] == "Дни рождения сегодня, 2 ноября:"
    assert "• Иван Иванов — 12 лет" in text
    assert "• Пётр Петров — 1 год" in text

# ---------------------------------------------------------------------------
# Условие отправки
# ---------------------------------------------------------------------------

def test_sends_after_digest_time_to_all_channels(
    monkeypatch, tutor_factory, student_factory
):
    """После времени отправки сообщение уходит во все привязанные каналы."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_factory(
        tutor_id=tutor_id, first_name="Иван", last_name="Петров",
        birth_date=date(2014, 11, 2),
    )
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)
        _connect(db, tutor_id, "max", MAX_CHAT_ID)

    assert _run() == 2

    assert len(calls) == 2
    telegram = next(call for call in calls if "api.telegram.org" in call["url"])
    assert telegram["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert telegram["data"]["chat_id"] == CHAT_ID
    max_call = next(call for call in calls if "max.ru" in call["url"])
    assert max_call["url"] == f"https://platform-api2.max.ru/messages?chat_id={MAX_CHAT_ID}"

    text = telegram["data"]["text"]
    assert "Дни рождения сегодня, 2 ноября:" in text
    assert "Иван Петров — 12 лет" in text
    # Оба канала получили одинаковый текст.
    assert _texts(calls) == [text, text]

    with SessionLocal() as db:
        assert get_param(db, tutor_id, BIRTHDAY_SENT_KEY) == "2026-11-02"

def test_silent_before_digest_time(monkeypatch, tutor_factory, student_factory):
    """До времени из профиля рассылки нет и день не помечается."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run(now=datetime(2026, 11, 2, 8, 59, tzinfo=UTC)) == 0

    assert calls == []
    with SessionLocal() as db:
        assert get_param(db, tutor_id, BIRTHDAY_SENT_KEY) is None

def test_custom_digest_time_is_respected(
    monkeypatch, tutor_factory, student_factory
):
    """Время отправки берётся из профиля (то же поле, что у дневной сводки)."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)
    _settings(tutor_id, digest_time="18:00")

    assert _run() == 0
    assert _run(now=datetime(2026, 11, 2, 18, 0, tzinfo=UTC)) == 1

def test_disabled_birthday_is_silent(monkeypatch, tutor_factory, student_factory):
    """Флаг «День рождения» выключен — сообщений нет и маркера нет."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)
    _settings(tutor_id, notify_birthday=False)

    assert _run() == 0
    assert calls == []
    with SessionLocal() as db:
        assert get_param(db, tutor_id, BIRTHDAY_SENT_KEY) is None

def test_second_run_same_day_is_silent(
    monkeypatch, tutor_factory, student_factory
):
    """Повторный прогон в тот же день ничего не отправляет."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1
    assert _run(now=datetime(2026, 11, 2, 23, 0, tzinfo=UTC)) == 0

    assert len(calls) == 1

def test_next_day_sends_again(monkeypatch, tutor_factory, student_factory):
    """На следующий день рассылка снова отправляется (для новых именинников)."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    student_factory(
        tutor_id=tutor_id, first_name="Второй", birth_date=date(2014, 11, 3)
    )
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 1
    assert _run(now=datetime(2026, 11, 3, 10, 0, tzinfo=UTC)) == 1

    assert len(calls) == 2
    assert "Дни рождения сегодня, 3 ноября:" in _texts(calls)[1]

def test_channel_without_chat_id_is_skipped(
    monkeypatch, tutor_factory, student_factory
):
    """Канал без привязанного чата в отправке не участвует."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)
        # Токен MAX есть, чат не привязан — канала фактически нет.
        set_param(db, tutor_id, token_key("max"), MAX_TOKEN)

    assert _run() == 1
    assert len(calls) == 1
    assert "api.telegram.org" in calls[0]["url"]

def test_no_bound_channel_is_silent(monkeypatch, tutor_factory, student_factory):
    """Нет привязанных каналов — ни сети, ни маркера."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))

    assert _run() == 0
    assert calls == []
    with SessionLocal() as db:
        assert get_param(db, tutor_id, BIRTHDAY_SENT_KEY) is None

def test_empty_list_sends_nothing_but_marks_day(
    monkeypatch, tutor_factory, student_factory
):
    """Нет именинников — сообщения нет, день помечен обработанным."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 5, 5))
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 0
    assert calls == []
    with SessionLocal() as db:
        assert get_param(db, tutor_id, BIRTHDAY_SENT_KEY) == "2026-11-02"

def test_channel_failure_does_not_raise(
    monkeypatch, tutor_factory, student_factory
):
    """Сбой единственного канала не поднимает исключение и не мешает второму."""
    calls = []
    _patch_urlopen(monkeypatch, calls, fail_messenger="telegram")
    tutor_id = tutor_factory()
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    assert _run() == 0

    with SessionLocal() as db:
        # День всё равно помечен: иначе сбойный канал ретраился бы до конца дня.
        assert get_param(db, tutor_id, BIRTHDAY_SENT_KEY) == "2026-11-02"

def test_tutor_timezone_shifts_sending_time(
    monkeypatch, tutor_factory, student_factory
):
    """Отправка идёт по настенному времени зоны педагога, а не по UTC."""
    calls = []
    _patch_urlopen(monkeypatch, calls)
    tutor_id = tutor_factory(timezone="Europe/Samara")  # UTC+4
    student_factory(tutor_id=tutor_id, birth_date=date(2014, 11, 2))
    with SessionLocal() as db:
        _connect(db, tutor_id, "telegram", CHAT_ID)

    # 04:59 UTC = 08:59 по Самаре — рано; 05:00 UTC = 09:00 — пора.
    assert _run(now=datetime(2026, 11, 2, 4, 59, tzinfo=UTC)) == 0
    assert _run(now=datetime(2026, 11, 2, 5, 0, tzinfo=UTC)) == 1

    assert len(calls) == 1
    with SessionLocal() as db:
        assert get_param(db, tutor_id, BIRTHDAY_SENT_KEY) == "2026-11-02"
