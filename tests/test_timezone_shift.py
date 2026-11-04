"""Смена часового пояса: пересчёт моментов времени при смене зоны.

Поведение проверяется на всех уровнях: чистый `shift_moment` (сохранение
настенного времени, отрицательный сдвиг, DST), сервис `shift_tutor_schedule`
(уроки, окна, ДЗ, списания), HTTP POST вкладки «Календарь» профиля и
критерий приёмки — HTML календаря до и после смены зоны совпадает по
времени карточек (меняется только бейдж зоны).
"""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.common.services.tutor_time import to_local
from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.homework.models.homework import Homework
from app.lesson.models.lesson import Lesson
from app.slot.models.slot import Slot
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import as_utc
from app.tutor.services.timezone_shift import shift_moment, shift_tutor_schedule

PASSWORD = "Секретный-Пароль-1"

# Зоны теста: UTC+04 → UTC+07 (3 часа вперёд по настенному времени).
OLD_ZONE = ZoneInfo("Europe/Ulyanovsk")  # UTC+4
NEW_ZONE = ZoneInfo("Asia/Krasnoyarsk")  # UTC+7


def _utc(value):
    """База данных хранит naive UTC (SQLite теряет tzinfo) — нормализуем."""
    return as_utc(value)


# ---------------------------------------------------------------------------
# Чистый сдвиг момента: настенное время сохраняется
# ---------------------------------------------------------------------------

def test_shift_moment_keeps_wall_time_forward():
    """UTC+04 → UTC+07: 10:00 настенных остаются 10:00, UTC 06:00 → 03:00."""
    shifted = shift_moment(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), OLD_ZONE, NEW_ZONE)
    assert shifted == datetime(2026, 10, 22, 3, 0, tzinfo=UTC)
    wall = shifted.astimezone(NEW_ZONE).replace(tzinfo=None)
    assert wall == datetime(2026, 10, 22, 10, 0)


def test_shift_moment_keeps_wall_time_backward():
    """UTC+07 → UTC+04: 10:00 настенных остаются 10:00, UTC 03:00 → 06:00."""
    shifted = shift_moment(
        datetime(2026, 10, 22, 3, 0, tzinfo=UTC), NEW_ZONE, OLD_ZONE
    )
    assert shifted == datetime(2026, 10, 22, 6, 0, tzinfo=UTC)


def test_shift_moment_naive_value_treated_as_utc():
    """SQLite хранит naive-значения UTC: наивный вход конвертится так же."""
    shifted = shift_moment(datetime(2026, 10, 22, 6, 0), OLD_ZONE, NEW_ZONE)
    assert shifted == datetime(2026, 10, 22, 3, 0, tzinfo=UTC)


def test_shift_moment_respects_dst_per_row():
    """Зона с переходом на летнее время: смещение зависит от даты.

    Europe/Berlin летом — UTC+2, зимой — UTC+1. Один и тот же настенный
    момент переводится по правилу «зашитое в строке смещение», поэтому для
    сравнения берём фиксированный UTC 09:00: летом это 11:00 настенных,
    зимой 10:00. Смещение в новой зоне (UTC+7) фиксировано, значит летом
    UTC-результат 04:00, зимой 03:00 — разница на час из-за перевода ломки
    в старой зоне.
    """
    berlin = ZoneInfo("Europe/Berlin")
    summer = shift_moment(datetime(2026, 7, 1, 9, 0, tzinfo=UTC), berlin, NEW_ZONE)
    winter = shift_moment(datetime(2026, 1, 1, 9, 0, tzinfo=UTC), berlin, NEW_ZONE)
    # Летом 09:00 UTC = 11:00 настенных, зимой = 10:00 → в UTC+7 это
    # 04:00 и 03:00 соответственно: сдвиг считается по строке, а не
    # фиксированным смещением.
    assert summer == datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
    assert winter == datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
    # Настенное время сохраняется в новой зоне: 11:00 летом, 10:00 зимой.
    assert summer.astimezone(NEW_ZONE).replace(tzinfo=None).time() == datetime(
        2026, 7, 1, 11, 0
    ).time()
    assert winter.astimezone(NEW_ZONE).replace(tzinfo=None).time() == datetime(
        2026, 1, 1, 10, 0
    ).time()


def test_shift_moment_old_equals_new_is_identity():
    """old == new: сдвиг ничего не меняет (включая написание зон)."""
    original = datetime(2026, 10, 22, 6, 0, tzinfo=UTC)
    assert shift_moment(original, OLD_ZONE, OLD_ZONE) == original


# ---------------------------------------------------------------------------
# Сервис: уроки, окна, ДЗ, списания
# ---------------------------------------------------------------------------

def _add_lesson(db, tutor_id, **overrides) -> str:
    """Урок с первым учеником репетитора; возвращает id урока."""
    from app.student.models.student import Student

    student = db.query(Student).filter_by(tutor_id=tutor_id).first()
    if student is None:
        student = Student(tutor_id=tutor_id, first_name="Ученик Сдвига")
        db.add(student)
        db.flush()
    values = {
        "student_id": student.id,
        "type": "individual",
        "starts_at": datetime(2026, 10, 22, 6, 0, tzinfo=UTC),
        "duration_min": 60,
        "status": "planned",
    }
    values.update(overrides)
    lesson = Lesson(**values)
    db.add(lesson)
    db.flush()
    return lesson.id


def test_shift_tutor_schedule_shifts_lessons_slots_homework_charges(tutor_factory):
    """Сдвиг пересчитывает уроки, окна, сроки ДЗ и списания."""
    from app.student.models.student import Student

    tutor_id = tutor_factory(timezone="Europe/Ulyanovsk")
    with SessionLocal() as db:
        lesson_id = _add_lesson(db, tutor_id, status="completed", price=1200)
        student = db.query(Student).filter_by(tutor_id=tutor_id).first()
        slot = Slot(
            tutor_id=tutor_id,
            starts_at=datetime(2026, 10, 22, 7, 0, tzinfo=UTC),
            duration_min=40,
        )
        homework = Homework(
            lesson_id=lesson_id,
            assignment="Задание на четверг",
            due_at=datetime(2026, 10, 25, 14, 0, tzinfo=UTC),
        )
        charge = AccountOperation(
            student_id=student.id,
            kind="lesson",
            amount=1200,
            occurred_at=datetime(2026, 10, 22, 6, 0, tzinfo=UTC),
            lesson_id=lesson_id,
        )
        db.add_all([slot, homework, charge])
        db.commit()

        counts = shift_tutor_schedule(db, tutor_id, OLD_ZONE, NEW_ZONE)
        db.commit()

    assert counts == {"lessons": 1, "slots": 1, "homework": 1, "charges": 1}
    with SessionLocal() as db:
        db_lesson = db.get(Lesson, lesson_id)
        db_slot = db.query(Slot).filter_by(tutor_id=tutor_id).one()
        db_homework = db.get(Homework, homework.id)
        db_charge = db.query(AccountOperation).filter_by(lesson_id=lesson_id).one()

    assert _utc(db_lesson.starts_at) == datetime(2026, 10, 22, 3, 0, tzinfo=UTC)
    assert _utc(db_slot.starts_at) == datetime(2026, 10, 22, 4, 0, tzinfo=UTC)
    assert _utc(db_homework.due_at) == datetime(2026, 10, 25, 11, 0, tzinfo=UTC)
    assert _utc(db_charge.occurred_at) == datetime(2026, 10, 22, 3, 0, tzinfo=UTC)


def test_shift_tutor_schedule_preserves_wall_time_in_db_value(tutor_factory):
    """UTC сменилось, но настенное время урока в новой зоне прежнее (10:00).

    Сервис не трогает поле `tutor.timezone` (его пишет вьюха) — поэтому
    настенное время проверяем в новой зоне явно.
    """
    tutor_id = tutor_factory(timezone="Europe/Ulyanovsk")
    with SessionLocal() as db:
        lesson_id = _add_lesson(db, tutor_id)
        db.commit()
        shift_tutor_schedule(db, tutor_id, OLD_ZONE, NEW_ZONE)
        db.commit()

    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
    assert _utc(lesson.starts_at) == datetime(2026, 10, 22, 3, 0, tzinfo=UTC)
    local = _utc(lesson.starts_at).astimezone(NEW_ZONE)
    assert (local.hour, local.minute) == (10, 0)


def test_shift_tutor_schedule_ignores_foreign_tutor(tutor_factory):
    """Чужой репетитор и его окно/ДЗ не трогаются сдвигом."""
    tutor_id = tutor_factory(timezone="Europe/Ulyanovsk")
    other_id = tutor_factory(timezone="Europe/Ulyanovsk")
    with SessionLocal() as db:
        other_lesson_id = _add_lesson(db, other_id)
        other_slot = Slot(
            tutor_id=other_id,
            starts_at=datetime(2026, 10, 22, 7, 0, tzinfo=UTC),
            duration_min=40,
        )
        other_homework = Homework(
            lesson_id=other_lesson_id,
            assignment="Чужое ДЗ",
            due_at=datetime(2026, 10, 25, 14, 0, tzinfo=UTC),
        )
        db.add_all([other_slot, other_homework])
        db.commit()
        shift_tutor_schedule(db, tutor_id, OLD_ZONE, NEW_ZONE)
        db.commit()

    with SessionLocal() as db:
        assert _utc(db.get(Lesson, other_lesson_id).starts_at) == datetime(2026, 10, 22, 6, 0, tzinfo=UTC)
        assert _utc(db.get(Slot, other_slot.id).starts_at) == datetime(2026, 10, 22, 7, 0, tzinfo=UTC)
        assert _utc(db.get(Homework, other_homework.id).due_at) == datetime(2026, 10, 25, 14, 0, tzinfo=UTC)


def test_shift_tutor_schedule_handles_slot_collision(tutor_factory):
    """Двухфазный сдвиг окна: коллизия с UNIQUE(tutor_id, starts_at).

    Окна 06:00 и 07:00 UTC при сдвиге +3 часа. Построчный апдейт дал бы
    IntegrityError (06:00 занимает место ещё не сдвинутого 07:00) ─
    двухфазная парковка сдвигает без ошибки.
    """
    tutor_id = tutor_factory(timezone="Europe/Ulyanovsk")
    with SessionLocal() as db:
        db.add_all([
            Slot(tutor_id=tutor_id, starts_at=datetime(2026, 10, 22, 6, 0, tzinfo=UTC), duration_min=40),
            Slot(tutor_id=tutor_id, starts_at=datetime(2026, 10, 22, 7, 0, tzinfo=UTC), duration_min=40),
        ])
        db.commit()
        counts = shift_tutor_schedule(db, tutor_id, OLD_ZONE, NEW_ZONE)
        db.commit()

    assert counts["slots"] == 2
    with SessionLocal() as db:
        starts = sorted(
            _utc(slot.starts_at)
            for slot in db.query(Slot).filter_by(tutor_id=tutor_id).all()
        )
    assert starts == [
        datetime(2026, 10, 22, 3, 0, tzinfo=UTC),
        datetime(2026, 10, 22, 4, 0, tzinfo=UTC),
    ]


def test_shift_tutor_schedule_handles_null_due_at(tutor_factory):
    """ДЗ без срока сдачи (due_at NULL) сдвигу не мешает и остаётся NULL."""
    tutor_id = tutor_factory(timezone="Europe/Ulyanovsk")
    with SessionLocal() as db:
        lesson_id = _add_lesson(db, tutor_id)
        homework = Homework(lesson_id=lesson_id, assignment="Без срока")
        db.add(homework)
        db.commit()
        shift_tutor_schedule(db, tutor_id, OLD_ZONE, NEW_ZONE)
        db.commit()

    with SessionLocal() as db:
        assert db.get(Homework, homework.id).due_at is None


# ---------------------------------------------------------------------------
# HTTP: сохранение вкладки «Календарь» со сменой зоны
# ---------------------------------------------------------------------------

def _register_and_login(client, email):
    client.post(
        "/tutor/register",
        data={
            "name": "Часовой",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )


def _calendar_form(timezone):
    return {
        "timezone": timezone,
        "quarter1_end": "10-25",
        "quarter2_end": "12-25",
        "quarter3_end": "03-20",
        "quarter4_end": "05-25",
        "workday_start": "09:00",
        "workday_end": "18:00",
        "default_lesson_duration": "60",
        "default_lesson_price": "1500",
    }


def _tutor_id_by_email(email):
    with SessionLocal() as db:
        return db.query(Tutor).filter_by(email=email).one().id


def test_profile_calendar_post_shifts_schedule(client):
    """POST вкладки «Календарь» сам пересчитывает урок/ДЗ и меняет зону."""
    email = "shift-http@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id_by_email(email)
    with SessionLocal() as db:
        # Регистрация ставит системную зону (в тестах CPI «автора» нет):
        # фиксируем исходную зону явно.
        db.get(Tutor, tutor_id).timezone = "Europe/Ulyanovsk"
        lesson_id = _add_lesson(db, tutor_id, status="completed", price=1200)
        homework_id = _add_homework(db, lesson_id, due_at=datetime(2026, 10, 25, 14, 0, tzinfo=UTC))
        db.commit()

    response = client.post(
        "/tutor/profile/calendar",
        data=_calendar_form("Asia/Krasnoyarsk"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/profile?tab=calendar&saved=1"

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        lesson = db.get(Lesson, lesson_id)
        homework = db.get(Homework, homework_id)
    assert tutor.timezone == "Asia/Krasnoyarsk"
    assert _utc(lesson.starts_at) == datetime(2026, 10, 22, 3, 0, tzinfo=UTC)
    assert _utc(homework.due_at) == datetime(2026, 10, 25, 11, 0, tzinfo=UTC)
    local = to_local(lesson.starts_at, tutor)
    assert (local.hour, local.minute) == (10, 0)


def _add_homework(db, lesson_id, **overrides):
    values = {"lesson_id": lesson_id, "assignment": "Домашнее задание"}
    values.update(overrides)
    homework = Homework(**values)
    db.add(homework)
    db.flush()
    return homework.id


def test_profile_calendar_keeps_lesson_when_zone_unchanged(client):
    """Сохранение той же зоны ничего не пересчитывает."""
    email = "shift-same@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id_by_email(email)
    with SessionLocal() as db:
        db.get(Tutor, tutor_id).timezone = "Europe/Ulyanovsk"
        lesson_id = _add_lesson(db, tutor_id)
        db.commit()

    response = client.post(
        "/tutor/profile/calendar",
        data=_calendar_form("Europe/Ulyanovsk"),
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        assert _utc(db.get(Lesson, lesson_id).starts_at) == datetime(2026, 10, 22, 6, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Критерий приёмки: календарь до и после смены зоны выглядит одинаково
# ---------------------------------------------------------------------------

def _event_cards(html):
    """Карточки-события: дата колонки, начало, длительность, подпись времени.

    `data-now` и `now_iso` — «сейчас» сервера и от запроса к запросу
    меняются; сравнение целого HTML неверно. Сравниваем карточки событий:
    дату, начало и длительность в минутах и подпись времени — то, что
    видит репетитор.
    """
    cards = re.findall(
        r'data-date="([^"]+)"\s+data-start-min="(\d+)"\s+data-duration-min="(\d+)"\s*[^>]*>'
        r'.*?<span class="cal-event__time">([^<]+)</span>',
        html,
        re.S,
    )
    return sorted(cards)


def test_calendar_html_identical_after_zone_change(client):
    """Приёмка: карточки календаря до и после смены зоны совпадают.

    Урок (и прошедший, и будущий) и окно созданы заранее; HTML календаря
    недели сравнивается до и после POST профиля со сменой зоны. Совпадают
    время начала, день и длительность карточек; меняется только бейдж
    зоны `.cal-tz`.
    """
    email = "shift-accept@example.com"
    _register_and_login(client, email)
    tutor_id = _tutor_id_by_email(email)
    with SessionLocal() as db:
        db.get(Tutor, tutor_id).timezone = "Europe/Ulyanovsk"
        # Два урока в одной неделе и окно для записи: прошедший (пн) и
        # будущий (чт) — сдвиг не должен различать их по времени.
        _add_lesson(db, tutor_id, starts_at=datetime(2026, 10, 12, 6, 0, tzinfo=UTC))
        _add_lesson(
            db,
            tutor_id,
            starts_at=datetime(2026, 10, 15, 13, 0, tzinfo=UTC),
            status="completed",
        )
        db.add(
            Slot(
                tutor_id=tutor_id,
                starts_at=datetime(2026, 10, 16, 7, 0, tzinfo=UTC),
                duration_min=40,
            )
        )
        db.commit()

    before = client.get("/tutor/calendar?start=2026-10-12").text

    response = client.post(
        "/tutor/profile/calendar",
        data=_calendar_form("Asia/Krasnoyarsk"),
        follow_redirects=False,
    )
    assert response.status_code == 303

    after = client.get("/tutor/calendar?start=2026-10-12").text

    assert _event_cards(before) == _event_cards(after)
    assert "Asia/Krasnoyarsk" in after
    assert "Europe/Ulyanovsk" not in after
