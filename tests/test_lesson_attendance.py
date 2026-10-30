"""Посещаемость группового урока (change group-lesson-attendance).

Проверяются сценарии спеки lesson-attendance и правки student-finance:
блок «Присутствие» в форме, разбор и сохранение отметок, исключение
отсутствовавших из списаний (возврат на баланс), баннер непересчитанного
баланса, счёт за период, пер-урочность отметок в серии и изоляция по
репетитору. HTTP-тесты идут теми же маршрутами и полями формы, что у
пользователя (правило AGENTS.md).
"""

import json
import re
from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import balance
from app.finance.services.charges import lesson_targets, sync_lesson_charge
from app.finance.services.invoice import priced_lessons
from app.finance.services.recalculate import has_missing_charges, recalculate
from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_attendance import LessonAttendance
from app.lesson.models.lesson_series import LessonSeries
from app.lesson.services.lesson_form import parse_attendance
from app.lesson.services.mass_update import apply_to_series
from app.tutor.models.tutor import Tutor

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="attendance@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "attendance@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def group_with_members(owner, group_factory, student_factory, group_member_factory):
    """Группа с ценой 1200 и двумя участниками; возвращает (id, [ученик1, ученик2])."""
    group_id = group_factory(tutor_id=owner, price_per_lesson=1200)
    first = student_factory(tutor_id=owner, first_name="Мария", last_name="Иванова")
    second = student_factory(tutor_id=owner, first_name="Пётр", last_name="Петров")
    group_member_factory(group_id=group_id, student_id=first)
    group_member_factory(group_id=group_id, student_id=second)
    return group_id, [first, second]


@pytest.fixture()
def group_lesson(lesson_factory, group_with_members):
    """Проведённый групповой урок группы; возвращает id."""
    group_id, _ = group_with_members
    return lesson_factory(group_id=group_id, price=None)


# --------------------------------------------------------------------------
# Хелперы
# --------------------------------------------------------------------------


def _mark(lesson_id: str, student_id: str, present: bool, reason: str | None = None):
    """Отметка посещаемости напрямую в БД (upsert, как пишет writer)."""
    with SessionLocal() as db:
        mark = db.scalars(
            select(LessonAttendance).where(
                LessonAttendance.lesson_id == lesson_id,
                LessonAttendance.student_id == student_id,
            )
        ).first()
        if mark is None:
            mark = LessonAttendance(
                lesson_id=lesson_id,
                student_id=student_id,
            )
            db.add(mark)
        mark.present = present
        mark.reason = reason
        db.commit()


def _marks(lesson_id: str) -> dict[str, tuple[bool, str | None]]:
    """Отметки урока: `{student_id: (present, reason)}`."""
    with SessionLocal() as db:
        rows = db.scalars(
            select(LessonAttendance).where(LessonAttendance.lesson_id == lesson_id)
        ).all()
        return {row.student_id: (row.present, row.reason) for row in rows}


def _charges(student_id: str) -> list[int]:
    """Суммы списаний ученика (kind='lesson')."""
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AccountOperation.amount).where(
                    AccountOperation.student_id == student_id,
                    AccountOperation.kind == "lesson",
                )
            ).all()
        )


def _tutor(tutor_id: str):
    """Карточка репетитора: сервисам счёта нужна её зона."""
    with SessionLocal() as db:
        return db.get(Tutor, tutor_id)


def _attendance_payload(records: list[dict]) -> str:
    return json.dumps(records)


def _record(student_id: str, present: bool, reason: str | None = None) -> dict:
    if present:
        return {"student_id": student_id, "present": True, "reason": None}
    return {"student_id": student_id, "present": False, "reason": reason}


def _group_form(group_id: str, **extra) -> dict:
    """Валидная форма сохранения группового урока (19.10.2026 10:00 UTC)."""
    data = {
        "type": "group",
        "group_id": group_id,
        "student_id": "",
        "starts_at": "2026-10-19T10:00",
        "duration_min": "60",
        "price": "",
        "note": "",
        "meeting_url": "",
        "status": "completed",
    }
    data.update(extra)
    return data


# --------------------------------------------------------------------------
# Модель: уникальность пары и инвариант reason
# --------------------------------------------------------------------------


def test_attendance_unique_and_reason_check(
    owner, group_lesson, group_with_members, expect_integrity_error
):
    """UNIQUE(lesson_id, student_id) и CHECK на `reason` (design D1)."""
    _, (first, second) = group_with_members

    # Валидная отметка отсутствия сохраняется.
    _mark(group_lesson, first, False, "excused")
    assert _marks(group_lesson) == {first: (False, "excused")}

    # Повторная отметка той же пары не сохраняется.
    with expect_integrity_error() as db:
        db.add(
            LessonAttendance(lesson_id=group_lesson, student_id=first, present=True)
        )
    # У присутствовавшего причины быть не должно.
    with expect_integrity_error() as db:
        db.add(
            LessonAttendance(
                lesson_id=group_lesson, student_id=second, present=True, reason="excused"
            )
        )
    # Причина вне закрытого списка не сохраняется.
    with expect_integrity_error() as db:
        db.add(
            LessonAttendance(
                lesson_id=group_lesson, student_id=second, present=False, reason="illness"
            )
        )
    assert _marks(group_lesson) == {first: (False, "excused")}


# --------------------------------------------------------------------------
# Правило списаний: lesson_targets / sync_lesson_charge
# --------------------------------------------------------------------------


def test_absent_member_excluded_from_targets(owner, group_lesson, group_with_members):
    """Задача 2.1: проведённый групповой урок списывает только присутствовавшим."""
    _, (first, second) = group_with_members
    _mark(group_lesson, second, False, "excused")

    with SessionLocal() as db:
        lesson = db.get(Lesson, group_lesson)
        targets = dict(lesson_targets(db, lesson))
    assert set(targets) == {first}
    assert targets[first] == 1200


def test_marking_absent_refunds_charge(owner, group_lesson, group_with_members):
    """Спека «Отметка отсутствия снимает списание»: баланс растёт на сумму."""
    _, (first, second) = group_with_members

    with SessionLocal() as db:
        lesson = db.get(Lesson, group_lesson)
        sync_lesson_charge(db, lesson)
        db.commit()
    assert sorted(_charges(first)) == [1200]
    assert sorted(_charges(second)) == [1200]

    _mark(group_lesson, second, False, "no_reason")
    with SessionLocal() as db:
        lesson = db.get(Lesson, group_lesson)
        sync_lesson_charge(db, lesson)
        db.commit()

    assert _charges(first) == [1200]
    assert _charges(second) == []
    # Возврат на баланс: у ученика не было платежей, баланс −1200 → 0.
    with SessionLocal() as db:
        assert balance(db, second) == 0


def test_back_to_present_restores_charge(owner, group_lesson, group_with_members):
    """Спека «Возврат в „присутствовал“ возвращает списание»."""
    _, (first, second) = group_with_members
    _mark(group_lesson, second, False, "excused")

    with SessionLocal() as db:
        lesson = db.get(Lesson, group_lesson)
        sync_lesson_charge(db, lesson)
        db.commit()
    assert _charges(second) == []

    # Отметка «отсутствовал» снята: причина не хранится (CHECK-инвариант).
    _mark(group_lesson, second, True, None)
    with SessionLocal() as db:
        lesson = db.get(Lesson, group_lesson)
        sync_lesson_charge(db, lesson)
        db.commit()
    assert _charges(second) == [1200]


def test_lesson_without_marks_keeps_targets(owner, group_lesson, group_with_members):
    """Спека «Урок без отметок — все присутствовали» (design D2)."""
    _, (first, second) = group_with_members
    with SessionLocal() as db:
        lesson = db.get(Lesson, group_lesson)
        assert len(lesson_targets(db, lesson)) == 2


# --------------------------------------------------------------------------
# Баннер непересчитанного баланса
# --------------------------------------------------------------------------


def test_banner_ignores_absent_member(owner, group_lesson, group_with_members):
    """Задача 2.2 / спека «Отсутствовавший не будит баннер» (design D4)."""
    _, (first, second) = group_with_members

    with SessionLocal() as db:
        assert has_missing_charges(db, owner, first)
        assert has_missing_charges(db, owner, second)

    _mark(group_lesson, second, False, "excused")

    with SessionLocal() as db:
        # У присутствовавшего без списания баннер есть, у отсутствовавшего — нет.
        assert has_missing_charges(db, owner, first)
        assert not has_missing_charges(db, owner, second)


# --------------------------------------------------------------------------
# Счёт за период
# --------------------------------------------------------------------------


def test_invoice_excludes_absent_completed_lesson(owner, group_lesson, group_with_members):
    """Задача 2.3 / спека «Занятие отсутствовавшего не в счёте» (design D5)."""
    _, (first, second) = group_with_members
    _mark(group_lesson, second, False, "excused")

    with SessionLocal() as db:
        tutor = _tutor(owner)
        lines = priced_lessons(db, second, date(2026, 10, 1), date(2026, 10, 31), tutor)
        lines_first = priced_lessons(
            db, first, date(2026, 10, 1), date(2026, 10, 31), tutor
        )
    assert lines == []
    assert [line["price"] for line in lines_first] == [1200]


def test_planned_lesson_with_mark_stays_in_invoice(
    owner, group_lesson, group_with_members, lesson_factory
):
    """Исключение — только у «Проведён»: отметка на плановом уроке счёт не выкидывает."""
    group_id, (first, _) = group_with_members
    planned = lesson_factory(group_id=group_id, price=None, status="planned")
    _mark(planned, first, False, "excused")
    _mark(group_lesson, first, False, "excused")

    with SessionLocal() as db:
        tutor = _tutor(owner)
        lines = priced_lessons(db, first, date(2026, 10, 1), date(2026, 10, 31), tutor)
    assert len(lines) == 1  # только плановый урок; проведённый с отметкой выпал


# --------------------------------------------------------------------------
# Пересчёт баланса
# --------------------------------------------------------------------------


def test_recalculate_respects_attendance(owner, group_lesson, group_with_members):
    """Задача 2.4 / спека «Пересчёт уважает посещаемость»; идемпотентность."""
    _, (first, second) = group_with_members
    _mark(group_lesson, second, False, "excused")

    with SessionLocal() as db:
        assert recalculate(db, owner, second) == 0
        assert recalculate(db, owner, first) == 1
    assert _charges(second) == []
    assert _charges(first) == [1200]

    # Повторный пересчёт ничего не меняет (спека «Повторный пересчёт»).
    with SessionLocal() as db:
        assert recalculate(db, owner, first) == 0
    assert _charges(first) == [1200]


# --------------------------------------------------------------------------
# Разбор формы: parse_attendance
# --------------------------------------------------------------------------


def test_parse_attendance_accepts_valid_list():
    records, error = parse_attendance(
        _attendance_payload([_record("id-1", True), _record("id-2", False, "excused")])
    )
    assert error is False
    assert records == [
        {"student_id": "id-1", "present": True, "reason": None},
        {"student_id": "id-2", "present": False, "reason": "excused"},
    ]


def test_parse_attendance_empty_field_is_noop():
    """Пустое поле — «отметки не присылались», а не «все отметки стереть»."""
    assert parse_attendance(None) == (None, False)
    assert parse_attendance("") == (None, False)


@pytest.mark.parametrize(
    ("raw", "expected_error"),
    [
        ("{не json", True),
        ('{"student_id": "id-1"}', True),  # объект вместо списка
        ('["id-1"]', True),  # элементы не объекты
        (_attendance_payload([{"student_id": "", "present": True}]), True),
        (_attendance_payload([{"student_id": "id-1", "present": "yes"}]), True),
        (_attendance_payload([{"student_id": "id-1", "present": True}]), False),
        (
            _attendance_payload([{"student_id": "id-1", "present": True, "reason": "excused"}]),
            True,  # причина у присутствовавшего
        ),
        (_attendance_payload([{"student_id": "id-1", "present": False}]), True),
        (
            _attendance_payload([{"student_id": "id-1", "present": False, "reason": "illness"}]),
            True,  # причина вне закрытого списка
        ),
    ],
)
def test_parse_attendance_rejects_malformed(raw, expected_error):
    """Мусорный JSON и неполные/невалидные записи — ошибка формы (design D7)."""
    records, error = parse_attendance(raw)
    assert error is expected_error
    if expected_error:
        assert records is None


# --------------------------------------------------------------------------
# Блок «Присутствие» в форме урока
# --------------------------------------------------------------------------


def test_group_edit_form_shows_attendance_block(owner, client, group_lesson, group_with_members):
    """Задача 4.1 / спека «Блок у группового урока»: участники и счётчик.

    Имена участников сервер в разметку не рендерит (список строит Alpine
    из `data-config`), поэтому конфиг разбирается из атрибута.
    """
    _, (first, second) = group_with_members
    _mark(group_lesson, second, False, "excused")

    page = client.get(f"/tutor/lessons/{group_lesson}/edit").text

    assert "Присутствие" in page
    assert "Все пришли" in page
    assert "Никто не пришёл" in page
    assert "Уважительная" in page
    assert "Без причины" in page
    # Скрытое поле уходит в форму урока.
    assert 'name="attendance"' in page

    config = re.search(r"data-config='(.*?)'", page, flags=re.S).group(1)
    attendance = json.loads(config)["attendance"]
    assert {member["student_id"] for member in attendance} == {first, second}
    by_id = {member["student_id"]: member for member in attendance}
    assert by_id[first] == {
        "student_id": first,
        "name": "Мария Иванова",
        "present": True,
        "reason": None,
    }
    assert by_id[second]["present"] is False
    assert by_id[second]["reason"] == "excused"


def test_block_absent_in_create_and_individual(owner, client, student_factory):
    """Спека: блока нет в создании урока и у негрупповых типов."""
    student = student_factory(tutor_id=owner, first_name="Мария")

    create_page = client.get("/tutor/lessons/new").text
    assert "Присутствие" not in create_page

    with SessionLocal() as db:
        lesson = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 19, 10, 0),
            duration_min=60,
            price=1200,
            status="completed",
        )
        db.add(lesson)
        db.commit()
        lesson_id = lesson.id

    edit_page = client.get(f"/tutor/lessons/{lesson_id}/edit").text
    assert "Присутствие" not in edit_page


# --------------------------------------------------------------------------
# Сохранение отметок через HTTP-форму
# --------------------------------------------------------------------------


def test_save_marks_and_refund_flow(owner, client, group_lesson, group_with_members):
    """Спека «Отметки сохраняются» + «Отметка отсутствия снимает списание»."""
    group_id, (first, second) = group_with_members

    with SessionLocal() as db:  # списания обоих участников
        sync_lesson_charge(db, db.get(Lesson, group_lesson))
        db.commit()

    payload = _attendance_payload(
        [_record(first, True), _record(second, False, "excused")]
    )
    response = client.post(
        f"/tutor/lessons/{group_lesson}",
        data=_group_form(group_id, attendance=payload),
        headers=HTMX,
    )
    assert response.status_code == 200

    marks = _marks(group_lesson)
    assert marks[first] == (True, None)
    assert marks[second] == (False, "excused")
    # Списание отсутствовавшего снято, присутствовавшего — на месте.
    assert _charges(first) == [1200]
    assert _charges(second) == []
    with SessionLocal() as db:
        assert balance(db, second) == 0

    # Повторное сохранение не дублирует отметки; возврат в «присутствовал»
    # восстанавливает списание.
    payload_back = _attendance_payload(
        [_record(first, True), _record(second, True)]
    )
    response = client.post(
        f"/tutor/lessons/{group_lesson}",
        data=_group_form(group_id, attendance=payload_back),
        headers=HTMX,
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        rows = db.scalars(
            select(LessonAttendance).where(LessonAttendance.lesson_id == group_lesson)
        ).all()
        assert len(rows) == 2
    assert _marks(group_lesson)[second] == (True, None)
    assert _charges(second) == [1200]


def test_save_without_attendance_field_keeps_marks(
    owner, client, group_lesson, group_with_members
):
    """Сохранение без поля `attendance` (нет JS, старая форма) отметки не трогает."""
    group_id, (first, _) = group_with_members
    _mark(group_lesson, first, False, "excused")

    response = client.post(
        f"/tutor/lessons/{group_lesson}", data=_group_form(group_id), headers=HTMX
    )
    assert response.status_code == 200
    assert _marks(group_lesson) == {first: (False, "excused")}


def test_save_ignores_foreign_student_id(owner, client, group_lesson, group_with_members, student_factory):
    """Чужой id в поле игнорируется (design D7), не ошибка."""
    group_id, (first, second) = group_with_members
    stranger = student_factory()

    payload = _attendance_payload(
        [_record(first, True), _record(second, True), _record(stranger, False, "excused")]
    )
    response = client.post(
        f"/tutor/lessons/{group_lesson}",
        data=_group_form(group_id, attendance=payload),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert set(_marks(group_lesson)) == {first, second}


def test_garbage_attendance_shows_form_error(owner, client, group_lesson, group_with_members):
    """Мусорное поле — ошибка формы, отметки не сохраняются."""
    group_id, (first, _) = group_with_members
    _mark(group_lesson, first, False, "excused")

    response = client.post(
        f"/tutor/lessons/{group_lesson}",
        data=_group_form(group_id, attendance="{не json"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert "Посещаемость: неверный формат данных." in response.text
    assert _marks(group_lesson) == {first: (False, "excused")}


def test_series_all_does_not_copy_marks(
    owner, client, group_with_members, group_lesson
):
    """Задача 3.4 / спека «Серия не получает отметки»: `attendance` вне whitelist."""
    group_id, (first, second) = group_with_members
    with SessionLocal() as db:
        lesson = db.get(Lesson, group_lesson)
        series = LessonSeries(
            slots=[{"weekday": 0, "start_time": "10:00", "end_time": "11:00"}],
            interval_weeks=1,
            until_date=date(2026, 11, 30),
        )
        db.add(series)
        db.flush()
        lesson.series_id = series.id
        sibling = Lesson(
            group_id=group_id,
            series_id=series.id,
            type="group",
            starts_at=datetime(2026, 10, 26, 10, 0),
            duration_min=60,
            price=None,
            status="completed",
        )
        db.add(sibling)
        db.commit()
        sibling_id = sibling.id

    payload = _attendance_payload([_record(first, True), _record(second, False, "excused")])
    response = client.post(
        f"/tutor/lessons/{group_lesson}",
        data=_group_form(group_id, attendance=payload, series_all="1"),
        headers=HTMX,
    )
    assert response.status_code == 200

    assert _marks(group_lesson) != {}
    assert _marks(sibling_id) == {}
    # Списания брата серии считаются по его отсутствию отметок: все присутствовали.
    assert _charges(second) == [1200]  # списание с урока-брата

    # Прямой вызов массового применения отметки не переносит: ключ
    # `attendance` не входит в whitelist `MASS_UPDATE_FIELDS`.
    with SessionLocal() as db:
        assert apply_to_series(db, lesson.series_id, {"attendance": payload}) == 2
    assert _marks(sibling_id) == {}


def test_foreign_tutor_gets_404_and_marks_untouched(
    client, tutor_factory, group_lesson, group_with_members
):
    """Задача 5.1 / спека «Чужой урок недоступен»: 404, отметки не изменены."""
    group_id, (first, second) = group_with_members
    _mark(group_lesson, first, False, "excused")

    stranger_email = "stranger-attendance@example.com"
    tutor_factory(email=stranger_email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": stranger_email, "password": PASSWORD},
        follow_redirects=False,
    )

    payload = _attendance_payload([_record(first, True), _record(second, True)])
    response = client.post(
        f"/tutor/lessons/{group_lesson}",
        data=_group_form(group_id, attendance=payload),
        headers=HTMX,
    )
    assert response.status_code == 404
    assert _marks(group_lesson) == {first: (False, "excused")}

    get_response = client.get(f"/tutor/lessons/{group_lesson}/edit")
    assert get_response.status_code == 404
