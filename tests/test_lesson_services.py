"""Сервисы модуля lesson: генерация серии, запись, mass-update, презентация."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.common.services.tutor_time import to_local
from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_series import LessonSeries
from app.lesson.services.lesson_writer import create_series, create_single_lesson
from app.lesson.services.mass_update import apply_to_series
from app.lesson.services.presentation import (
    format_price,
    format_rating,
    format_target,
    status_label,
    type_chip_label,
)
from app.lesson.services.series_generator import generate_occurrences
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import as_utc


def _tutor(tutor_id: str) -> SimpleNamespace:
    """Карточка репетитора: сервисам нужен только её часовой пояс.

    Простой объект, а не ORM-строка: значение читается внутри сессии и
    переживает её закрытие (спека tutor-timezone — зона участвует в
    разборе формы и записи серии).
    """
    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        return SimpleNamespace(timezone=tutor.timezone)

# --------------------------------------------------------------------------
# Генерация серии (2.1)
# --------------------------------------------------------------------------

_MONDAY_0 = 0  # понедельник (как в date.weekday())
_THURSDAY = 3


def test_generate_mondays_from_start_to_until_inclusive():
    """Спека: начало 19.10.2026 10:00, «Пн 10:00», 1 нед. до 09.11.2026
    — все понедельники с 19.10 по 09.11 включительно."""
    starts_at = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    slots = [
        {"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"}
    ]

    occurrences = generate_occurrences(
        starts_at=starts_at,
        slots=slots,
        interval_weeks=1,
        until_date=date(2026, 11, 9),
    )

    assert occurrences == [
        datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
        datetime(2026, 10, 26, 10, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
        datetime(2026, 11, 9, 10, 0, tzinfo=UTC),
    ]


def test_generate_first_occurrence_is_not_before_start():
    """Слот в четверг при начале в понедельник: первая дата — 22.10."""
    starts_at = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    slots = [
        {"weekday": _THURSDAY, "start_time": "15:00", "end_time": "16:00"}
    ]

    occurrences = generate_occurrences(
        starts_at=starts_at,
        slots=slots,
        interval_weeks=1,
        until_date=date(2026, 10, 29),
    )

    assert occurrences == [
        datetime(2026, 10, 22, 15, 0, tzinfo=UTC),
        datetime(2026, 10, 29, 15, 0, tzinfo=UTC),
    ]


def test_generate_multiple_slots_produce_their_own_weekdays():
    """Два слота (Пн и Чт): в каждой неделе серии по два урока."""
    starts_at = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    slots = [
        {"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"},
        {"weekday": _THURSDAY, "start_time": "15:00", "end_time": "16:00"},
    ]

    occurrences = sorted(
        generate_occurrences(
            starts_at=starts_at,
            slots=slots,
            interval_weeks=1,
            until_date=date(2026, 11, 5),
        )
    )

    # Отсортированные по времени: в каждой неделе по два урока, в своих днях.
    assert [occurrence.weekday() for occurrence in occurrences] == [
        _MONDAY_0,
        _THURSDAY,
        _MONDAY_0,
        _THURSDAY,
        _MONDAY_0,
        _THURSDAY,
    ]
    assert occurrences[1] == datetime(2026, 10, 22, 15, 0, tzinfo=UTC)


def test_generate_interval_greater_than_one_week():
    """Интервал 2 недели: даты через две недели, до окончания включительно."""
    starts_at = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    slots = [{"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"}]

    occurrences = generate_occurrences(
        starts_at=starts_at,
        slots=slots,
        interval_weeks=2,
        until_date=date(2026, 11, 2),
    )

    assert occurrences == [
        datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
    ]


def test_generate_naive_starts_at_stays_naive():
    """Naive `starts_at` даёт naive даты (часовой пояс не выдумывается)."""
    starts_at = datetime(2026, 10, 19, 10, 0)
    slots = [{"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"}]

    occurrences = generate_occurrences(
        starts_at=starts_at,
        slots=slots,
        interval_weeks=1,
        until_date=date(2026, 10, 19),
    )

    assert occurrences == [datetime(2026, 10, 19, 10, 0)]


def test_generate_rejects_empty_slots():
    """Пустой список слотов — ошибка, а не тихо пустая серия."""
    with pytest.raises(ValueError, match="расписания"):
        generate_occurrences(
            starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            slots=[],
            interval_weeks=1,
            until_date=date(2026, 11, 9),
        )


def test_generate_rejects_bad_repeat_parameters():
    """Без даты окончания, с интервалом < 1 недели и с кривым слотом — ошибка."""
    starts_at = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    slots = [{"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"}]

    with pytest.raises(ValueError, match="окончания"):
        generate_occurrences(starts_at, slots, interval_weeks=1, until_date=None)
    with pytest.raises(ValueError, match="Интервал"):
        generate_occurrences(starts_at, slots, interval_weeks=0, until_date=date(2026, 11, 9))
    with pytest.raises(ValueError, match="Слот №1"):
        generate_occurrences(
            starts_at,
            [{"weekday": 7, "start_time": "10:00", "end_time": "11:00"}],
            interval_weeks=1,
            until_date=date(2026, 11, 9),
        )
    with pytest.raises(ValueError, match="Слот №1"):
        generate_occurrences(
            starts_at,
            [{"weekday": _MONDAY_0, "start_time": "в десять", "end_time": "11:00"}],
            interval_weeks=1,
            until_date=date(2026, 11, 9),
        )


def test_generate_guards_against_endless_series():
    """Защита от «бесконечной» серии: потолок числа уроков срабатывает."""
    from app.lesson.services.series_generator import MAX_SERIES_OCCURRENCES

    starts_at = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    slots = [{"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"}]

    with pytest.raises(ValueError, match="Серия слишком длинная"):
        generate_occurrences(
            starts_at=starts_at,
            slots=slots,
            interval_weeks=1,
            until_date=date(9999, 12, 31),
        )
    # Ровно по потолоку — ещё проходит.
    until = starts_at.date() + timedelta_weeks(MAX_SERIES_OCCURRENCES - 1)
    occurrences = generate_occurrences(starts_at, slots, 1, until)
    assert len(occurrences) == MAX_SERIES_OCCURRENCES


def timedelta_weeks(weeks: int) -> timedelta:
    """Таймдельта ровно в N недель (хелпер теста)."""
    return timedelta(weeks=weeks)


# --------------------------------------------------------------------------
# Запись урока (2.2)
# --------------------------------------------------------------------------


def _lesson_data(**overrides) -> dict:
    """Данные валидной формы создания индивидуального урока."""
    data = {
        "student_id": None,
        "group_id": None,
        "type": "individual",
        "starts_at": datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
        "duration_min": 60,
        "note": None,
        "meeting_url": None,
        "price": None,
        "repeat": False,
        "slots": [],
        "interval_weeks": 1,
        "until_date": None,
    }
    data.update(overrides)
    return data


def test_create_single_lesson_saves_one_lesson(tutor_factory, student_factory):
    """Одиночный урок: создаётся один Lesson без серии, статус «Запланирован»."""
    tutor_id = tutor_factory()
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        lesson, errors = create_single_lesson(
            db,
            _lesson_data(student_id=student_id, price=1200, note="Квадратные уравнения"),
            tutor,
        )

    assert errors == []
    assert lesson.id is not None
    assert lesson.series_id is None
    assert lesson.status == "planned"
    with SessionLocal() as db:
        assert db.query(Lesson).count() == 1
        assert db.query(LessonSeries).count() == 0


def test_create_single_lesson_requires_start(tutor_factory, student_factory):
    """Пустое начало: урок не создаётся, форма получает ошибку."""
    tutor_id = tutor_factory()
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        lesson, errors = create_single_lesson(
            db, _lesson_data(student_id=student_id, starts_at=None), tutor
        )

    assert lesson is None
    assert errors == ["Укажите начало урока."]
    with SessionLocal() as db:
        assert db.query(Lesson).count() == 0


def test_create_lesson_goal_must_match_type(tutor_factory, student_factory, group_factory):
    """Цель не по типу: групповому — группа, остальным — ученик."""
    tutor_id = tutor_factory()
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    group_id = group_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        lesson, errors = create_single_lesson(
            db, _lesson_data(group_id=group_id), tutor  # индивидуальный с группой
        )
    assert lesson is None
    assert "выберите ученика" in errors[0].lower()

    with SessionLocal() as db:
        lesson, errors = create_single_lesson(
            db,
            _lesson_data(type="group", student_id=student_id),  # групповой с учеником
            tutor,
        )
    assert lesson is None
    assert "выберите группу" in errors[0].lower()


def test_create_lesson_duration_outside_closed_list_rejected(
    tutor_factory, student_factory
):
    """Длительность вне `LESSON_DURATIONS` (80) отклоняется валидацией."""
    tutor_id = tutor_factory()
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        lesson, errors = create_single_lesson(
            db, _lesson_data(student_id=student_id, duration_min=80), tutor
        )

    assert lesson is None
    assert errors == ["Выберите длительность урока из списка."]


def test_create_series_materializes_all_lessons(tutor_factory, student_factory):
    """Спека: начало 19.10.2026 10:00, «Пн 10:00», 1 нед. до 09.11 —
    четыре понедельника одной серии."""
    tutor_id = tutor_factory()
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    data = _lesson_data(
        student_id=student_id,
        repeat=True,
        slots=[{"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"}],
        interval_weeks=1,
        until_date=date(2026, 11, 9),
    )

    with SessionLocal() as db:
        lessons, errors = create_series(db, data, tutor)

    assert errors == []
    assert len(lessons) == 4
    series_ids = {lesson.series_id for lesson in lessons}
    assert None not in series_ids and len(series_ids) == 1
    with SessionLocal() as db:
        saved = db.query(Lesson).order_by(Lesson.starts_at).all()
        assert [lesson.starts_at.date() for lesson in saved] == [
            date(2026, 10, 19),
            date(2026, 10, 26),
            date(2026, 11, 2),
            date(2026, 11, 9),
        ]
        assert {lesson.status for lesson in saved} == {"planned"}
        assert all(lesson.duration_min == 60 for lesson in saved)
        series = db.query(LessonSeries).one()
        assert series.until_date == date(2026, 11, 9)
        assert series.interval_weeks == 1
        assert series.slots == data["slots"]


def test_create_series_without_until_date_rejected(tutor_factory, student_factory):
    """Повтор без даты окончания блокирует сохранение (спека)."""
    tutor_id = tutor_factory()
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    data = _lesson_data(
        student_id=student_id,
        repeat=True,
        slots=[{"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"}],
        until_date=None,
    )

    with SessionLocal() as db:
        lessons, errors = create_series(db, data, tutor)

    assert lessons == []
    assert errors == ["Укажите дату окончания повтора."]
    with SessionLocal() as db:
        assert db.query(Lesson).count() == 0
        assert db.query(LessonSeries).count() == 0


def test_create_series_empty_slots_rejected(tutor_factory, student_factory):
    """Включённый повтор с пустой панелью расписания не сохраняется."""
    tutor_id = tutor_factory()
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    data = _lesson_data(
        student_id=student_id, repeat=True, slots=[], until_date=date(2026, 11, 9)
    )

    with SessionLocal() as db:
        lessons, errors = create_series(db, data, tutor)

    assert lessons == []
    assert errors == ["Панель расписания пуста: добавьте хотя бы один слот."]


def test_create_series_is_atomic_on_bad_slot(tutor_factory, student_factory):
    """Кривой слот: ни серия, ни уроки не сохранены (одна транзакция)."""
    tutor_id = tutor_factory()
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    data = _lesson_data(
        student_id=student_id,
        repeat=True,
        slots=[
            {"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"},
            {"weekday": 99, "start_time": "15:00", "end_time": "16:00"},
        ],
        until_date=date(2026, 11, 9),
    )

    with SessionLocal() as db:
        lessons, errors = create_series(db, data, tutor)

    assert lessons == []
    assert errors and "Слот №2" in errors[0]
    with SessionLocal() as db:
        assert db.query(Lesson).count() == 0
        assert db.query(LessonSeries).count() == 0


def test_create_series_keeps_tutor_weekday_in_utc_plus4(tutor_factory, student_factory):
    """Спека (задача 4.2): серия «по четвергам 10:00» при зоне UTC+04.

    Перевод начала в UTC не сдвигает день недели: каждая дата серии в
    зоне педагога — четверг, и настенное время 10:00 сохраняется.
    """
    tutor_id = tutor_factory(timezone="Europe/Ulyanovsk")
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    data = _lesson_data(
        student_id=student_id,
        repeat=True,
        slots=[{"weekday": _THURSDAY, "start_time": "10:00", "end_time": "11:00"}],
        interval_weeks=1,
        until_date=date(2026, 11, 5),
    )

    with SessionLocal() as db:
        lessons, errors = create_series(db, data, tutor)

    assert errors == []
    with SessionLocal() as db:
        saved = db.query(Lesson).order_by(Lesson.starts_at).all()
    # В зоне педагога каждая дата — четверг и ровно 10:00 (UTC+04 без DST).
    assert [to_local(lesson.starts_at, tutor).weekday() for lesson in saved] == [
        _THURSDAY,
        _THURSDAY,
        _THURSDAY,
    ]
    assert [to_local(lesson.starts_at, tutor).strftime("%H:%M") for lesson in saved] == [
        "10:00",
        "10:00",
        "10:00",
    ]
    # Хранение — UTC: 10:00 в UTC+04 это 06:00 UTC того же дня.
    assert [as_utc(lesson.starts_at) for lesson in saved] == [
        datetime(2026, 10, 22, 6, 0, tzinfo=UTC),
        datetime(2026, 10, 29, 6, 0, tzinfo=UTC),
        datetime(2026, 11, 5, 6, 0, tzinfo=UTC),
    ]


def test_create_series_across_dst_keeps_wall_time(tutor_factory, student_factory):
    """Спека (задача 4.3): серия через перевод часов в Europe/Berlin.

    Настенное время 10:00 сохраняется по обе стороны перевода (29.03.2026),
    а UTC-значения соседних недель различаются на час: 23.03 — CET (+01),
    30.03 и 06.04 — CEST (+02).
    """
    tutor_id = tutor_factory(timezone="Europe/Berlin")
    tutor = _tutor(tutor_id)
    student_id = student_factory(tutor_id=tutor_id)
    data = _lesson_data(
        student_id=student_id,
        # 23.03.2026 10:00 в Berlin (CET) = 09:00 UTC — понедельник.
        starts_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
        repeat=True,
        slots=[{"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"}],
        interval_weeks=1,
        until_date=date(2026, 4, 6),
    )

    with SessionLocal() as db:
        lessons, errors = create_series(db, data, tutor)

    assert errors == []
    with SessionLocal() as db:
        saved = db.query(Lesson).order_by(Lesson.starts_at).all()
    # Настенное время в зоне педагога не съезжает: все понедельники в 10:00.
    assert [
        to_local(lesson.starts_at, tutor).strftime("%Y-%m-%d %H:%M") for lesson in saved
    ] == ["2026-03-23 10:00", "2026-03-30 10:00", "2026-04-06 10:00"]
    # В UTC недели через перевод отличаются на 6 дней 23 часа, а не на 7.
    assert [as_utc(lesson.starts_at) for lesson in saved] == [
        datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
        datetime(2026, 3, 30, 8, 0, tzinfo=UTC),
        datetime(2026, 4, 6, 8, 0, tzinfo=UTC),
    ]


# --------------------------------------------------------------------------
# Массовое редактирование серии (2.3)
# --------------------------------------------------------------------------


def _create_series_lessons(
    tutor_id: str, student_id: str, count: int = 3
) -> tuple[str, list[str]]:
    """Создаёт серию уроков по понедельникам; возвращает (series_id, уроки)."""
    data = _lesson_data(
        student_id=student_id,
        price=1200,
        repeat=True,
        slots=[{"weekday": _MONDAY_0, "start_time": "10:00", "end_time": "11:00"}],
        interval_weeks=1,
        until_date=date(2026, 10, 19) + timedelta(weeks=count - 1),
    )
    with SessionLocal() as db:
        lessons, errors = create_series(db, data, _tutor(tutor_id))
    assert errors == []
    return lessons[0].series_id, [lesson.id for lesson in lessons]


def test_mass_update_applies_common_fields_to_all_lessons(
    tutor_factory, student_factory
):
    """Массовое изменение типа трогает все уроки серии, включая прошедшие."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    series_id, lesson_ids = _create_series_lessons(tutor_id, student_id)

    with SessionLocal() as db:
        touched = apply_to_series(
            db,
            series_id,
            {
                "type": "trial",
                "student_id": student_id,
                "group_id": None,
                "duration_min": 90,
                "meeting_url": "https://example.com/meet/series",
                "price": 1500,
            },
        )

    assert touched == 3
    with SessionLocal() as db:
        saved = {
            lesson.id: lesson
            for lesson in db.query(Lesson).where(Lesson.id.in_(lesson_ids))
        }
        assert {lesson.type for lesson in saved.values()} == {"trial"}
        assert {lesson.duration_min for lesson in saved.values()} == {90}
        assert {lesson.price for lesson in saved.values()} == {1500}
        assert {lesson.meeting_url for lesson in saved.values()} == {
            "https://example.com/meet/series"
        }
        # Первая дата серии (19.10.2026) уже прошла — правка применилась.
        assert min(lesson.starts_at for lesson in saved.values()).date() == date(
            2026, 10, 19
        )


def test_mass_update_ignores_per_lesson_fields(tutor_factory, student_factory):
    """Оценка, статус, комментарий и заметка не массовые (спека)."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    series_id, _ = _create_series_lessons(tutor_id, student_id)

    with SessionLocal() as db:
        lesson = db.query(Lesson).first()
        lesson.rating = 5
        lesson.status = "completed"
        lesson.family_comment = "Отлично!"
        lesson.note = "Своя заметка урока"
        db.commit()

    with SessionLocal() as db:
        apply_to_series(
            db,
            series_id,
            {
                "type": "practice",
                "student_id": student_id,
                "group_id": None,
                "duration_min": 60,
                "meeting_url": None,
                "price": 1000,
                # Пер-уточные поля в том же POST — не должны примениться.
                "status": "planned",
                "rating": 1,
                "family_comment": "Общий комментарий",
                "note": "Общая заметка",
            },
        )

    with SessionLocal() as db:
        saved_lesson = db.query(Lesson).first()
        assert saved_lesson.type == "practice"  # общее поле применилось
        assert saved_lesson.rating == 5
        assert saved_lesson.status == "completed"
        assert saved_lesson.family_comment == "Отлично!"
        assert saved_lesson.note == "Своя заметка урока"


def test_mass_update_does_not_touch_other_series(tutor_factory, student_factory):
    """Уроки других серий и одиночные уроки не затрагиваются."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    series_id, _ = _create_series_lessons(tutor_id, student_id)
    other_series_id, other_ids = _create_series_lessons(tutor_id, student_id)
    with SessionLocal() as db:
        single = create_single_lesson(
            db, _lesson_data(student_id=student_id, price=700), _tutor(tutor_id)
        )[0]

    with SessionLocal() as db:
        apply_to_series(db, series_id, {"price": 999, "student_id": student_id})

    with SessionLocal() as db:
        other = {
            lesson.id: lesson
            for lesson in db.query(Lesson).where(Lesson.id.in_(other_ids))
        }
        assert {lesson.price for lesson in other.values()} == {1200}
        assert {lesson.series_id for lesson in other.values()} == {other_series_id}
        assert db.get(Lesson, single.id).price == 700


# --------------------------------------------------------------------------
# Презентация (2.4)
# --------------------------------------------------------------------------


def test_format_price_completed_lesson_is_paid():
    """«1 200 ₽ (Оплачено)» — проведённый урок с оплатой (спека)."""
    assert (
        format_price(1200, lesson_type="individual", status="completed")
        == "1\u00a0200\u00a0₽ (Оплачено)"
    )


def test_format_price_planned_lesson_has_no_suffix():
    assert (
        format_price(1200, lesson_type="trial", status="planned")
        == "1\u00a0200\u00a0₽"
    )


def test_format_price_group_lesson_is_dash():
    """У группового урока в колонке стоимости — прочерк (спека)."""
    assert format_price(1200, lesson_type="group", status="completed") == "—"


def test_format_price_without_price_is_dash():
    """Цена не задана — прочерк, без суффикса оплаты."""
    assert format_price(None, lesson_type="individual", status="completed") == "—"


def test_format_target_shows_group_prefix():
    """Групповой урок — «Группа: <имя>», остальные — ученик (спека)."""
    assert format_target("Аня Иванова", None, "individual") == "Аня Иванова"
    assert format_target(None, "Группа А", "group") == "Группа: Группа А"


def test_type_chip_label_uses_russian_labels():
    assert type_chip_label("trial") == "Пробный"
    assert type_chip_label("group") == "Групповой"
    # Неизвестное значение не роняет шаблон.
    assert type_chip_label("webinar") == "webinar"


def test_status_label():
    assert status_label("planned") == "Запланирован"
    assert status_label("completed") == "Проведён"


def test_format_rating_stars():
    """Оценка 3 — «★★★☆☆», без оценки — пустая строка."""
    assert format_rating(3) == "★★★☆☆"
    assert format_rating(5) == "★★★★★"
    assert format_rating(None) == ""
