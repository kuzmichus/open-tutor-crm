"""Тесты сервисов недоступности: доступ, покрытие недели, форма, запись, предупреждение.

Проверяются чистые сервисы (без HTTP) — вьюхи и разметка панели
проверяются отдельно в `test_unavailability_panel.py`.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.database import SessionLocal
from app.unavailability.models.unavailability import TutorUnavailability
from app.unavailability.services.access import get_owned_unavailability
from app.unavailability.services.marks import (
    coverage_for_week,
    list_marks,
    marks_for_week,
    week_days,
)
from app.unavailability.services.presentation import (
    format_span,
    reason_label,
    weekday_label,
)
from app.unavailability.services.unavailability_form import (
    mark_rows,
    parse_unavailability_form,
    validate_end_change,
    validate_unavailability_data,
)
from app.unavailability.services.unavailability_writer import (
    change_end,
    create_mark,
    delete_mark,
)
from app.unavailability.services.warning import unavailability_warning

# Неделя 12–18 октября 2026: понедельник … воскресенье.
MONDAY = date(2026, 10, 12)
SUNDAY = date(2026, 10, 18)


def _get(mark_id: str) -> TutorUnavailability:
    """Отметка из БД по id."""
    with SessionLocal() as db:
        return db.get(TutorUnavailability, mark_id)


# --------------------------------------------------------------------------
# 2.1 Доступ: только своя отметка, чужая — 404
# --------------------------------------------------------------------------


def test_get_owned_unavailability_returns_own_mark(tutor_factory, unavailability_factory):
    """Своя отметка находится по id."""
    tutor_id = tutor_factory()
    mark_id = unavailability_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        mark = get_owned_unavailability(db, mark_id, tutor_id)
        assert mark.id == mark_id


@pytest.mark.parametrize(
    "mark_exists", [True, False], ids=["foreign-mark", "missing-mark"]
)
def test_get_owned_unavailability_hides_foreign_and_missing(
    mark_exists, tutor_factory, unavailability_factory
):
    """Чужая и несуществующая отметка неразличимы — обе 404, а не 403."""
    owner_id = tutor_factory()
    stranger_id = tutor_factory()
    mark_id = (
        unavailability_factory(tutor_id=owner_id) if mark_exists else "no-such-mark"
    )

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as error:
            get_owned_unavailability(db, mark_id, stranger_id)
    assert error.value.status_code == 404


# --------------------------------------------------------------------------
# 2.2 Покрытие недели: бессрочный период, бессрочный выходной, приоритет
# --------------------------------------------------------------------------


def test_week_days_are_seven_from_monday():
    """Неделя — семь дат от понедельника."""
    days = week_days(MONDAY)
    assert len(days) == 7
    assert days[0] == MONDAY
    assert days[-1] == SUNDAY


def test_marks_for_week_selects_only_overlapping_marks(
    tutor_factory, unavailability_factory
):
    """В выборку недели попадают только пересекающиеся отметки."""
    tutor_id = tutor_factory()
    inside = unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 10, 14),
        end_date=date(2026, 10, 15),
    )
    # Прошлая неделя и следующая — не пересекаются.
    unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 3),
    )
    unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 10, 26),
        end_date=date(2026, 10, 30),
    )

    with SessionLocal() as db:
        marks = marks_for_week(db, tutor_id, MONDAY)
    assert [mark.id for mark in marks] == [inside]


def test_coverage_of_period_with_open_end_is_unbounded(
    tutor_factory, unavailability_factory
):
    """Период без последнего дня покрывает все дни начиная с первого."""
    tutor_id = tutor_factory()
    unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 10, 14),
        end_date=None,
    )

    with SessionLocal() as db:
        coverage = coverage_for_week(db, tutor_id, MONDAY)
        # И неделя спустя — тоже покрыта.
        later = coverage_for_week(db, tutor_id, MONDAY + timedelta(days=7))

    assert set(coverage) == {
        date(2026, 10, 14),
        date(2026, 10, 15),
        date(2026, 10, 16),
        date(2026, 10, 17),
        date(2026, 10, 18),
    }
    assert all(mark.reason_label == "Отпуск" for mark in coverage.values())
    assert len(later) == 7


def test_coverage_of_weekday_without_until_date_is_unbounded(
    tutor_factory, unavailability_factory
):
    """Постоянный выходной без «Действует по» покрывает каждую такую неделю."""
    tutor_id = tutor_factory()
    unavailability_factory(tutor_id=tutor_id, mode="weekday", weekday=5)

    with SessionLocal() as db:
        this_week = coverage_for_week(db, tutor_id, MONDAY)
        next_week = coverage_for_week(db, tutor_id, MONDAY + timedelta(days=7))

    assert set(this_week) == {date(2026, 10, 17)}
    assert this_week[date(2026, 10, 17)].reason_label == "Выходной"
    assert set(next_week) == {date(2026, 10, 24)}


def test_coverage_of_weekday_respects_until_date(
    tutor_factory, unavailability_factory
):
    """«Действует по» ограничивает выходной: позже дни свободны."""
    tutor_id = tutor_factory()
    unavailability_factory(
        tutor_id=tutor_id,
        mode="weekday",
        weekday=5,
        until_date=date(2026, 10, 17),
    )

    with SessionLocal() as db:
        this_week = coverage_for_week(db, tutor_id, MONDAY)
        next_week = coverage_for_week(db, tutor_id, MONDAY + timedelta(days=7))

    assert set(this_week) == {date(2026, 10, 17)}
    assert next_week == {}


def test_period_reason_wins_over_weekday(tutor_factory, unavailability_factory):
    """Приоритет D4: причина периода в шапке, выходной — в подсказке."""
    tutor_id = tutor_factory()
    # Суббота 17.10 попадает и в период (больничный), и в выходной.
    unavailability_factory(
        tutor_id=tutor_id,
        reason="sick",
        start_date=date(2026, 10, 16),
        end_date=date(2026, 10, 18),
    )
    unavailability_factory(tutor_id=tutor_id, mode="weekday", weekday=5)

    with SessionLocal() as db:
        coverage = coverage_for_week(db, tutor_id, MONDAY)

    saturday = coverage[date(2026, 10, 17)]
    assert saturday.reason == "sick"
    assert saturday.reason_label == "Больничный"
    assert saturday.extra_reasons == ("Выходной",)
    # Остальные дни периода — без «Выходного» в подсказке.
    assert coverage[date(2026, 10, 16)].extra_reasons == ()


def test_coverage_ignores_other_tutors(
    tutor_factory, unavailability_factory
):
    """Покрытие считается только по отметкам вошедшего репетитора."""
    owner_id = tutor_factory()
    stranger_id = tutor_factory()
    unavailability_factory(
        tutor_id=stranger_id,
        start_date=MONDAY,
        end_date=SUNDAY,
    )

    with SessionLocal() as db:
        assert coverage_for_week(db, owner_id, MONDAY) == {}


def test_coverage_empty_week_is_empty_dict(tutor_factory):
    """Неделя без отметок — пустой словарь (шаблон проверяет ключ)."""
    tutor_id = tutor_factory()

    with SessionLocal() as db:
        assert coverage_for_week(db, tutor_id, MONDAY) == {}


# --------------------------------------------------------------------------
# 2.3 Разбор формы: причины, даты, день недели
# --------------------------------------------------------------------------


def test_parse_period_form():
    """Валидная форма периода разбирается в значения без ошибок."""
    data, errors = parse_unavailability_form(
        {
            "mode": "period",
            "reason": "sick",
            "start_date": "2026-10-26",
            "end_date": "2026-10-30",
        }
    )

    assert errors == []
    assert data["mode"] == "period"
    assert data["reason"] == "sick"
    assert data["start_date"] == date(2026, 10, 26)
    assert data["end_date"] == date(2026, 10, 30)


def test_parse_period_form_with_empty_end_is_unbounded():
    """Пустой последний день — бессрочно, без ошибки."""
    data, errors = parse_unavailability_form(
        {"mode": "period", "reason": "vacation", "start_date": "2026-10-26"}
    )

    assert errors == []
    assert data["end_date"] is None


@pytest.mark.parametrize(
    ("form", "expected_error"),
    [
        # Причина вне закрытого списка.
        (
            {"mode": "period", "reason": "holiday", "start_date": "2026-10-26"},
            "Выберите причину недоступности.",
        ),
        # Первый день обязателен.
        (
            {"mode": "period", "reason": "vacation", "start_date": ""},
            "Укажите первый день.",
        ),
        # Конец раньше начала.
        (
            {
                "mode": "period",
                "reason": "vacation",
                "start_date": "2026-10-30",
                "end_date": "2026-10-26",
            },
            "Последний день не раньше первого.",
        ),
        # Кривая дата — ошибка разбора, а не тихое игнорирование.
        (
            {"mode": "period", "reason": "vacation", "start_date": "26.10.2026"},
            "Укажите корректный первый день.",
        ),
        # День недели обязателен.
        ({"mode": "weekday", "weekday": ""}, "Выберите день недели."),
        # День недели вне 0–6.
        ({"mode": "weekday", "weekday": "9"}, "Выберите день недели."),
    ],
    ids=[
        "reason-not-in-list",
        "no-start-date",
        "end-before-start",
        "broken-start-date",
        "no-weekday",
        "weekday-out-of-range",
    ],
)
def test_form_rejections(form, expected_error):
    """Невалидная форма отклоняется с подписью ошибки из закрытых списков."""
    _, errors = parse_unavailability_form(form)

    assert expected_error in errors


def test_parse_weekday_form():
    """Постоянный выходной: день недели и необязательное «Действует по»."""
    data, errors = parse_unavailability_form(
        {"mode": "weekday", "weekday": "5", "until_date": "2026-12-31"}
    )

    assert errors == []
    assert data["mode"] == "weekday"
    assert data["weekday"] == 5
    assert data["until_date"] == date(2026, 12, 31)


def test_unknown_mode_is_rejected():
    """Неизвестный режим отклоняется."""
    assert validate_unavailability_data({"mode": "other"}) == [
        "Выберите режим отметки."
    ]


# --------------------------------------------------------------------------
# 2.4 Запись: создание, изменение срока, снятие; подписи срока
# --------------------------------------------------------------------------


def test_create_period_mark(tutor_factory):
    """Создание отметки периода сохраняет причину и обе даты."""
    tutor_id = tutor_factory()
    data = {
        "mode": "period",
        "reason": "vacation",
        "start_date": date(2026, 10, 26),
        "end_date": date(2026, 10, 30),
    }

    with SessionLocal() as db:
        mark, errors = create_mark(db, tutor_id, data)
        mark_id = mark.id

    assert errors == []
    saved = _get(mark_id)
    assert saved.tutor_id == tutor_id
    assert saved.reason == "vacation"
    assert saved.weekday is None
    assert saved.until_date is None


def test_create_weekday_mark_forces_dayoff_reason(tutor_factory):
    """Причина постоянного выходного — всегда «Выходной», даже если в форме другая."""
    tutor_id = tutor_factory()
    data = {
        "mode": "weekday",
        "reason": "vacation",
        "weekday": 6,
    }

    with SessionLocal() as db:
        mark, errors = create_mark(db, tutor_id, data)
        mark_id = mark.id

    assert errors == []
    saved = _get(mark_id)
    assert saved.reason == "dayoff"
    assert saved.weekday == 6
    assert saved.start_date is None
    assert saved.end_date is None


def test_create_mark_with_invalid_data_writes_nothing(tutor_factory):
    """Ошибка валидации не создаёт запись."""
    tutor_id = tutor_factory()

    with SessionLocal() as db:
        mark, errors = create_mark(db, tutor_id, {"mode": "period"})

    assert mark is None
    assert errors
    with SessionLocal() as db:
        assert db.scalars(select(TutorUnavailability)).all() == []


def test_change_end_to_none_makes_period_unbounded(
    tutor_factory, unavailability_factory
):
    """Пустой новый срок делает период бессрочным."""
    tutor_id = tutor_factory()
    mark_id = unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 10, 26),
        end_date=date(2026, 10, 30),
    )

    with SessionLocal() as db:
        mark = db.get(TutorUnavailability, mark_id)
        assert change_end(db, mark, None) == []

    assert _get(mark_id).end_date is None


def test_validate_end_change_allows_shortening_past_mark():
    """Сократить прошедшую отметку можно: «не раньше сегодня» не требуется."""

    class _Mark:
        mode = "period"
        start_date = date(2020, 1, 1)

    assert validate_end_change(_Mark(), date(2020, 1, 5)) == []


def test_delete_mark_frees_days(tutor_factory, unavailability_factory):
    """Снятие освобождает дни: покрытие недели становится пустым.

    HTTP-путь «Снять» проверяется в `test_unavailability_panel.py`; здесь —
    инвариант сервиса: удалённая отметка больше не покрывает дни.
    """
    tutor_id = tutor_factory()
    mark_id = unavailability_factory(
        tutor_id=tutor_id, start_date=MONDAY, end_date=SUNDAY
    )

    with SessionLocal() as db:
        mark = db.get(TutorUnavailability, mark_id)
        delete_mark(db, mark)
        assert coverage_for_week(db, tutor_id, MONDAY) == {}

    assert _get(mark_id) is None


@pytest.mark.parametrize(
    ("mark", "expected"),
    [
        # Период с двумя датами.
        (
            SimpleNamespace(
                mode="period",
                start_date=date(2026, 10, 26),
                end_date=date(2026, 10, 30),
                weekday=None,
                until_date=None,
            ),
            "26.10 – 30.10",
        ),
        # Период без последнего дня.
        (
            SimpleNamespace(
                mode="period",
                start_date=date(2026, 10, 26),
                end_date=None,
                weekday=None,
                until_date=None,
            ),
            "с 26.10 — бессрочно",
        ),
        # Постоянный выходной без «Действует по».
        (
            SimpleNamespace(
                mode="weekday",
                start_date=None,
                end_date=None,
                weekday=5,
                until_date=None,
            ),
            "сб, бессрочно",
        ),
        # Постоянный выходной с «Действует по».
        (
            SimpleNamespace(
                mode="weekday",
                start_date=None,
                end_date=None,
                weekday=6,
                until_date=date(2026, 12, 31),
            ),
            "вс, по 31.12",
        ),
    ],
    ids=["period", "period-unbounded", "weekday", "weekday-until"],
)
def test_format_span(mark, expected):
    """Срок отметки одной строкой — по форматам из docstring модуля."""
    assert format_span(mark) == expected


def test_reason_and_weekday_labels():
    """Подписи причин и дней недели — из закрытых списков модели."""

    class _Mark:
        reason = "sick"

    assert reason_label(_Mark()) == "Больничный"
    assert weekday_label(5) == "сб"
    assert weekday_label(None) == ""


def test_mark_rows_put_active_first_and_past_under_section(
    tutor_factory, unavailability_factory
):
    """Порядок списка D11: активные по возрастанию, прошедшие отдельно."""
    tutor_id = tutor_factory()
    future = unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 6),
    )
    past = unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 5),
    )

    with SessionLocal() as db:
        rows = mark_rows(list_marks(db, tutor_id), today=date(2026, 10, 22))

    assert [row.mark.id for row in rows] == [future, past]
    assert [row.is_past for row in rows] == [False, True]


# --------------------------------------------------------------------------
# 2.5 Предупреждение о постановке урока в отмеченный день
# --------------------------------------------------------------------------


def test_warning_is_none_without_marks(tutor_factory):
    """Свободные дни и пустой список дат — предупреждения нет.

    Пустой список приходит, когда у серии не оказалось дат; `date` вместо
    `datetime` — когда вызывающий уже отбросил время. Оба варианта
    принимаются, но отметок нет — предупреждать не о чем.
    """
    tutor_id = tutor_factory()

    with SessionLocal() as db:
        assert unavailability_warning(
            db, tutor_id, [datetime(2026, 10, 14, 10, 0)]
        ) is None
        assert unavailability_warning(db, tutor_id, []) is None
        assert unavailability_warning(db, tutor_id, [date(2026, 10, 14)]) is None


def test_warning_counts_dates_inside_marks(tutor_factory, unavailability_factory):
    """Число совпадает с числом дат, попавших в отмеченные дни."""
    tutor_id = tutor_factory()
    unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 10, 14),
        end_date=date(2026, 10, 16),
    )
    occurrences = [
        datetime(2026, 10, 12, 10, 0),  # понедельник — свободен
        datetime(2026, 10, 14, 10, 0),  # среда — отмечена
        datetime(2026, 10, 16, 10, 0),  # пятница — отмечена
    ]

    with SessionLocal() as db:
        warning = unavailability_warning(db, tutor_id, occurrences)

    assert warning == ("Отпуск", 2)


def test_warning_names_reason_of_mark(tutor_factory, unavailability_factory):
    """Причина в предупреждении — подпись отметки."""
    tutor_id = tutor_factory()
    unavailability_factory(
        tutor_id=tutor_id,
        mode="weekday",
        weekday=2,
    )

    with SessionLocal() as db:
        warning = unavailability_warning(
            db, tutor_id, [datetime(2026, 10, 14, 10, 0)]
        )

    assert warning == ("Выходной", 1)


def test_warning_counts_each_date_once(tutor_factory, unavailability_factory):
    """Две отметки на один день не удваивают счёт: считаются занятия."""
    tutor_id = tutor_factory()
    unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 10, 14),
        end_date=date(2026, 10, 14),
    )
    unavailability_factory(tutor_id=tutor_id, mode="weekday", weekday=2)

    with SessionLocal() as db:
        warning = unavailability_warning(
            db, tutor_id, [datetime(2026, 10, 14, 10, 0)]
        )

    assert warning == ("Отпуск", 1)


def test_warning_handles_series_across_weeks(tutor_factory, unavailability_factory):
    """Серия через несколько недель: покрытие считается по неделям."""
    tutor_id = tutor_factory()
    unavailability_factory(
        tutor_id=tutor_id,
        start_date=date(2026, 10, 19),
        end_date=date(2026, 10, 25),
    )
    occurrences = [
        datetime(2026, 10, 12, 10, 0),  # свободная неделя
        datetime(2026, 10, 19, 10, 0),  # отмеченная неделя
        datetime(2026, 10, 21, 10, 0),  # отмеченная неделя
        datetime(2026, 10, 26, 10, 0),  # снова свободная
    ]

    with SessionLocal() as db:
        warning = unavailability_warning(db, tutor_id, occurrences)

    assert warning == ("Отпуск", 2)


def test_warning_ignores_other_tutors(tutor_factory, unavailability_factory):
    """Чужие отметки не предупреждают."""
    owner_id = tutor_factory()
    stranger_id = tutor_factory()
    unavailability_factory(
        tutor_id=stranger_id,
        start_date=date(2026, 10, 14),
        end_date=date(2026, 10, 14),
    )

    with SessionLocal() as db:
        assert unavailability_warning(
            db, owner_id, [datetime(2026, 10, 14, 10, 0)]
        ) is None
