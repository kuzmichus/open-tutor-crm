"""Тесты пачки окон: разбор формы, генерация, пропуски и лимит.

`plan()` и `apply()` — один расчёт (design.md D6), поэтому предпросмотр не
может разойтись с результатом: это проверяется отдельным тестом сравнением
`report.create` с фактически созданными окнами.

Пачка частичная: конфликтующие окна пропускаются с причиной, остальные
создаются — осознанное расхождение с атомарной серией уроков (design.md
Risks).
"""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.slot.models.slot import Slot
from app.slot.services.batch import (
    SKIP_BUSY_LESSON,
    SKIP_BUSY_SLOT,
    SKIP_PAST,
    SKIP_UNAVAILABLE_DAY,
    apply,
    batch_coverage,
    plan,
    plan_for_tutor,
)
from app.slot.services.slot_form import (
    MAX_SLOT_BATCH,
    BatchParams,
    parse_batch_form,
    parse_slot_form,
)

# Понедельник 12.10.2026; неделя 12.10–18.10.
MONDAY = date(2026, 10, 12)
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _tutor(tutor_id: str = "tutor-1", timezone: str = "UTC") -> SimpleNamespace:
    """Карточка репетитора для сервисов пачки: id и зона."""
    return SimpleNamespace(id=tutor_id, timezone=timezone)


def _params(**overrides) -> BatchParams:
    """Параметры пачки по умолчанию: один понедельник, 10:00–18:00, 40 + 15."""
    values = {
        "date_from": MONDAY,
        "date_to": MONDAY,
        "weekdays": (0,),
        "day_start": time(10, 0),
        "day_end": time(18, 0),
        "duration_min": 40,
        "gap_min": 15,
        "is_public": True,
    }
    values.update(overrides)
    return BatchParams(**values)


def _form(**overrides):
    """Подделка `FormData`: `get` и `getlist` для повторяющихся полей."""
    values = {
        "date_from": "2026-10-12",
        "date_to": "2026-10-12",
        "weekdays": ["0"],
        "day_start": "10:00",
        "day_end": "18:00",
        "duration_min": "40",
        "gap_min": "15",
        "is_public": "on",
    }
    values.update(overrides)

    class _Form:
        def get(self, name, default=""):
            value = values.get(name, default)
            if isinstance(value, list):
                return value[0] if value else default
            return value

        def getlist(self, name):
            value = values.get(name, [])
            return list(value) if isinstance(value, list) else [value]

    return _Form()


def _plan(**overrides):
    """`plan()` с пустыми занятиями по умолчанию."""
    params = overrides.pop("params", None) or _params()
    options = {
        "tutor": _tutor(),
        "lessons": [],
        "slots": [],
        "coverage": {},
        "now": NOW,
    }
    options.update(overrides)
    return plan(params, **options)


# --------------------------------------------------------------------------
# 3.1 Разбор формы
# --------------------------------------------------------------------------


def test_valid_batch_form_has_no_errors():
    """Валидная форма пачки ошибок не даёт и разбирается в параметры."""
    params, errors = parse_batch_form(_form())

    assert errors == []
    assert params.date_from == MONDAY
    assert params.date_to == MONDAY
    assert params.weekdays == (0,)
    assert params.day_start == time(10, 0)
    assert params.day_end == time(18, 0)
    assert params.duration_min == 40
    assert params.gap_min == 15
    assert params.is_public is True


def test_batch_form_keeps_only_selected_weekdays():
    """Дни недели приходят повторяющимся полем и нормализуются."""
    params, errors = parse_batch_form(_form(weekdays=["3", "1", "3"]))

    assert errors == []
    assert params.weekdays == (1, 3)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"weekdays": []}, "Выберите хотя бы один день недели."),
        (
            {"date_from": "2026-10-20", "date_to": "2026-10-12"},
            "Конец периода не раньше начала.",
        ),
        (
            {"day_start": "18:00", "day_end": "10:00"},
            "Время «До» должно быть позже «Окна с».",
        ),
        (
            {"day_start": "10:00", "day_end": "10:00"},
            "Время «До» должно быть позже «Окна с».",
        ),
        ({"duration_min": "80"}, "Выберите длительность окна из списка."),
        ({"gap_min": "-5"}, "Перерыв — от 0 до 240 минут."),
    ],
    ids=[
        "no-weekdays",
        "end-before-start",
        "day-end-before-start",
        "equal-day-bounds",
        "bad-duration",
        "negative-gap",
    ],
)
def test_batch_form_rejections(overrides, message):
    """Невалидная форма пачки отклоняется одним своим сообщением."""
    _, errors = parse_batch_form(_form(**overrides))

    assert errors == [message]


def test_batch_form_requires_period():
    """Пустой период — ошибки обоих полей."""
    _, errors = parse_batch_form(_form(date_from="", date_to=""))

    assert "Укажите начало периода." in errors
    assert "Укажите конец периода." in errors


def test_valid_single_slot_form_has_no_errors():
    """Валидная форма одного окна разбирается в значения."""
    params, errors = parse_slot_form(
        _form(date="2026-10-14", time="14:00", duration_min="45", is_public="on")
    )

    assert errors == []
    assert params.starts_at == datetime(2026, 10, 14, 14, 0)
    assert params.duration_min == 45
    assert params.is_public is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"date": ""}, "Укажите дату окна."),
        ({"time": ""}, "Укажите время начала окна."),
        ({"duration_min": "80"}, "Выберите длительность окна из списка."),
        ({"date": "2026-13-45"}, "Укажите корректную дату окна."),
    ],
    ids=["no-date", "no-time", "bad-duration", "broken-date"],
)
def test_single_slot_form_errors_are_specific(overrides, message):
    """Каждая ошибка формы одного окна — своё сообщение."""
    values = {"date": "2026-10-14", "time": "14:00", "duration_min": "40"}
    values.update(overrides)

    _, errors = parse_slot_form(_form(**values))

    assert message in errors


# --------------------------------------------------------------------------
# 3.2 Генерация: шаг «длительность + перерыв», лимит, недоступный день
# --------------------------------------------------------------------------


def test_day_generation_steps_by_duration_plus_gap():
    """10:00–18:00, 40 минут, перерыв 15 → девять окон 10:00…17:20."""
    report = _plan()

    assert report.errors == ()
    assert len(report.create) == 9
    assert [start.strftime("%H:%M") for start in report.create] == [
        "10:00",
        "10:55",
        "11:50",
        "12:45",
        "13:40",
        "14:35",
        "15:30",
        "16:25",
        "17:20",
    ]


def test_last_window_does_not_exceed_day_end():
    """Окно, которое закончилось бы позже «До», не создаётся.

    10:00–11:20, длительность 40, перерыв 0 → 10:00 и 10:40; третье
    окно (11:20–12:00) уже за концом интервала.
    """
    report = plan(
        _params(day_start=time(10, 0), day_end=time(11, 20), gap_min=0),
        tutor=_tutor(),
        lessons=[],
        slots=[],
        coverage={},
        now=NOW,
    )

    assert [start.strftime("%H:%M") for start in report.create] == ["10:00", "10:40"]


def test_batch_covers_selected_weekdays_of_period():
    """Пачка идёт по выбранным дням недели внутри периода включительно."""
    # 12.10 (пн) – 25.10 (вс), вторники и четверга.
    report = plan(
        _params(
            date_from=date(2026, 10, 12),
            date_to=date(2026, 10, 25),
            weekdays=(1, 3),
            day_start=time(10, 0),
            day_end=time(11, 0),
            duration_min=40,
            gap_min=0,
        ),
        tutor=_tutor(),
        lessons=[],
        slots=[],
        coverage={},
        now=NOW,
    )

    days = sorted({start.date() for start in report.create})
    assert days == [
        date(2026, 10, 13),
        date(2026, 10, 15),
        date(2026, 10, 20),
        date(2026, 10, 22),
    ]
    assert all(day.weekday() in (1, 3) for day in days)


def test_batch_beyond_limit_is_rejected_without_windows():
    """201 окно отклоняется: ошибка формы, ни одного окна."""
    # 11 дней × 20 окон = 220 > 200.
    report = plan(
        _params(
            date_from=date(2026, 10, 12),
            date_to=date(2026, 10, 22),
            weekdays=(0, 1, 2, 3, 4, 5, 6),
            day_start=time(8, 0),
            day_end=time(18, 0),
            duration_min=30,
            gap_min=0,
        ),
        tutor=_tutor(),
        lessons=[],
        slots=[],
        coverage={},
        now=NOW,
    )

    assert report.create == ()
    assert report.errors
    assert str(MAX_SLOT_BATCH) in report.errors[0]


def test_batch_at_limit_is_allowed():
    """Ровно 200 окон — допустимая пачка."""
    # 10 дней × 20 окон = 200.
    report = plan(
        _params(
            date_from=date(2026, 10, 12),
            date_to=date(2026, 10, 21),
            weekdays=(0, 1, 2, 3, 4, 5, 6),
            day_start=time(8, 0),
            day_end=time(18, 0),
            duration_min=30,
            gap_min=0,
        ),
        tutor=_tutor(),
        lessons=[],
        slots=[],
        coverage={},
        now=NOW,
    )

    assert report.errors == ()
    assert len(report.create) == MAX_SLOT_BATCH


def test_unavailable_day_is_skipped_with_reason():
    """День отпуска даёт пропуски `unavailable_day`, остальные создаются."""
    from app.unavailability.services.marks import DayMark

    report = plan(
        _params(
            date_from=date(2026, 10, 12),
            date_to=date(2026, 10, 13),
            weekdays=(0, 1),
            day_start=time(10, 0),
            day_end=time(11, 20),
            duration_min=40,
            gap_min=0,
        ),
        tutor=_tutor(),
        lessons=[],
        slots=[],
        coverage={date(2026, 10, 13): DayMark(reason="vacation", reason_label="Отпуск")},
        now=NOW,
    )

    assert [start.date() for start in report.create] == [date(2026, 10, 12)] * 2
    assert {skip.reason for skip in report.skip} == {SKIP_UNAVAILABLE_DAY}
    assert len(report.skip) == 2


def test_past_window_is_skipped():
    """Прошедшие окна не создаются: причина `past`."""
    report = plan(
        _params(date_from=date(2026, 9, 1), date_to=date(2026, 9, 1), weekdays=(1,)),
        tutor=_tutor(),
        lessons=[],
        slots=[],
        coverage={},
        now=NOW,
    )

    assert report.create == ()
    assert {skip.reason for skip in report.skip} == {SKIP_PAST}


@pytest.mark.parametrize(
    ("busy", "reason"),
    [("lessons", SKIP_BUSY_LESSON), ("slots", SKIP_BUSY_SLOT)],
    ids=["busy-lesson", "busy-slot"],
)
def test_busy_window_is_skipped(busy, reason):
    """Окно поверх занятия или существующего окна пропускается со своей причиной."""
    conflict_start = datetime(2026, 10, 12, 13, 40, tzinfo=UTC)
    report = _plan(**{busy: [(conflict_start, conflict_start + timedelta(minutes=40))]})

    assert len(report.create) == 8
    assert [skip.reason for skip in report.skip] == [reason]


def test_batch_uses_tutor_zone_for_utc_conversion():
    """Настенное время педагога переводится в UTC по его зоне.

    Педагог в UTC+04: окно 10:00 его времени = 06:00 UTC.
    """
    report = plan(
        _params(day_end=time(10, 40), gap_min=0),
        tutor=_tutor(timezone="Europe/Samara"),
        lessons=[],
        slots=[],
        coverage={},
        now=NOW,
    )

    assert report.create[0] == datetime(2026, 10, 12, 6, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# 3.3 apply(): частичное создание, повторный запуск без дублей
# --------------------------------------------------------------------------


def _save_lesson(tutor_id: str, student_id: str, starts_at: datetime, duration_min: int = 40) -> str:
    """Урок напрямую в БД."""
    with SessionLocal() as session:
        lesson = Lesson(
            student_id=student_id,
            type="individual",
            starts_at=starts_at,
            duration_min=duration_min,
            status="planned",
        )
        session.add(lesson)
        session.commit()
        return lesson.id


def test_apply_creates_only_non_conflicting_windows(tutor_factory, student_factory):
    """Из 18 окон с двумя конфликтами создано 16, в отчёте два пропуска."""
    from app.tutor.models.tutor import Tutor

    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    # Два понедельника по 9 окон = 18; конфликты — в первом дне.
    _save_lesson(tutor_id, student_id, datetime(2026, 10, 12, 11, 50, tzinfo=UTC))
    _save_lesson(tutor_id, student_id, datetime(2026, 10, 12, 15, 30, tzinfo=UTC))

    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        created, report = apply(
            session,
            tutor,
            _params(
                date_from=date(2026, 10, 12),
                date_to=date(2026, 10, 19),
                weekdays=(0,),
            ),
            now=NOW,
        )

    assert len(created) == 16
    assert len(report.skip) == 2
    assert {skip.reason for skip in report.skip} == {SKIP_BUSY_LESSON}

    with SessionLocal() as session:
        assert session.query(Slot).filter_by(tutor_id=tutor_id).count() == 16


def test_apply_twice_does_not_create_duplicates(tutor_factory):
    """Повторный `apply` с теми же параметрами не создаёт дублей."""
    from app.tutor.models.tutor import Tutor

    tutor_id = tutor_factory()
    params = _params(day_end=time(11, 20), gap_min=0)

    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        created, _ = apply(session, tutor, params, now=NOW)
    assert len(created) == 2

    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        created, report = apply(session, tutor, params, now=NOW)

    assert created == []
    assert {skip.reason for skip in report.skip} == {SKIP_BUSY_SLOT}

    with SessionLocal() as session:
        assert session.query(Slot).filter_by(tutor_id=tutor_id).count() == 2


def test_apply_rejects_over_limit_without_writing(tutor_factory):
    """Пачка сверх лимита не создаёт ни одного окна."""
    from app.tutor.models.tutor import Tutor

    tutor_id = tutor_factory()
    params = _params(
        date_from=date(2026, 10, 12),
        date_to=date(2026, 10, 22),
        weekdays=(0, 1, 2, 3, 4, 5, 6),
        day_start=time(8, 0),
        day_end=time(18, 0),
        duration_min=30,
        gap_min=0,
    )

    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        created, report = apply(session, tutor, params, now=NOW)

    assert created == []
    assert report.errors

    with SessionLocal() as session:
        assert session.query(Slot).filter_by(tutor_id=tutor_id).count() == 0


def test_apply_keeps_publicity_flag(tutor_factory):
    """Признак публичности из формы попадает в созданные окна."""
    from app.tutor.models.tutor import Tutor

    tutor_id = tutor_factory()
    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        apply(
            session,
            tutor,
            _params(day_end=time(10, 40), gap_min=0, is_public=False),
            now=NOW,
        )

    with SessionLocal() as session:
        slots = session.query(Slot).filter_by(tutor_id=tutor_id).all()
    assert len(slots) == 1
    assert slots[0].is_public is False


def test_batch_coverage_merges_several_weeks(tutor_factory, unavailability_factory):
    """Недоступность периода пачки собирается по всем её неделям."""
    tutor_id = tutor_factory()
    # Отпуск 26.10–30.10.2026 (неделя 26.10) — пачка 12.10–30.10.
    unavailability_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        coverage = batch_coverage(
            session, tutor_id, date(2026, 10, 12), date(2026, 10, 30)
        )

    assert date(2026, 10, 26) in coverage
    assert coverage[date(2026, 10, 26)].reason == "vacation"
    assert date(2026, 10, 12) not in coverage


def test_plan_for_tutor_reads_lessons_and_coverage(tutor_factory, student_factory):
    """`plan_for_tutor` учитывает уроки и отметки из БД."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    _save_lesson(tutor_id, student_id, datetime(2026, 10, 12, 10, 55, tzinfo=UTC))

    from app.tutor.models.tutor import Tutor

    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        report = plan_for_tutor(session, tutor, _params(), now=NOW)

    assert len(report.create) == 8
    assert [skip.reason for skip in report.skip] == [SKIP_BUSY_LESSON]


# --------------------------------------------------------------------------
# 3.4 Предпросмотр совпадает с созданием
# --------------------------------------------------------------------------


def test_preview_matches_apply_result(tutor_factory, student_factory):
    """`plan()` и `apply()` при неизменных параметрах дают один набор времён."""
    from app.tutor.models.tutor import Tutor

    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    _save_lesson(tutor_id, student_id, datetime(2026, 10, 12, 13, 40, tzinfo=UTC))

    params = _params()

    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        preview = plan_for_tutor(session, tutor, params, now=NOW)

    with SessionLocal() as session:
        tutor = session.get(Tutor, tutor_id)
        created, report = apply(session, tutor, params, now=NOW)

    assert tuple(slot.starts_at.replace(tzinfo=UTC) for slot in created) == preview.create
    assert tuple(slot.starts_at.replace(tzinfo=UTC) for slot in created) == report.create
    assert {skip.reason for skip in report.skip} == {skip.reason for skip in preview.skip}
