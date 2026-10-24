"""Списания из путей записи урока (задачи 5.3–5.5).

Проверяется не сам `sync_lesson_charge` (он покрыт в
`test_finance_charges.py`), а то, что он **вызван** в каждом пути записи
урока: создание, правка, массовая правка серии и удаление. Пропущенный
путь — это расхождение урока и счёта, которое пользователь увидит только
по баннеру «Баланс не пересчитан» (design D8).

Тесты идут HTTP-путём там, где путь HTTP-ный: те же маршруты и поля формы,
что у пользователя (правило AGENTS.md).
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import balance
from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_series import LessonSeries
from app.lesson.services.lesson_writer import create_series, create_single_lesson
from app.tutor.models.tutor import Tutor

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="lesson-charges@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "lesson-charges@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _tutor(session, tutor_id: str):
    """Карточка репетитора: сервису записи нужна только её зона."""
    tutor = session.get(Tutor, tutor_id)
    return SimpleNamespace(timezone=tutor.timezone)


def _lesson_data(student_id: str, price: int | None = 1200, **extra) -> dict:
    """Данные валидного создания индивидуального урока."""
    data = {
        "student_id": student_id,
        "group_id": None,
        "type": "individual",
        "starts_at": datetime(2026, 10, 19, 10, 0),
        "duration_min": 60,
        "price": price,
        "repeat": False,
        "slots": [],
    }
    data.update(extra)
    return data


def _create_completed_lesson(owner: str, student_id: str, price: int = 1200):
    """Проведённый урок через сервис записи: создаёт урок и его списание."""
    with SessionLocal() as session:
        lesson, errors = create_single_lesson(
            session,
            _lesson_data(student_id, price, status="completed"),
            _tutor(session, owner),
        )
    assert errors == []
    return lesson


def _charges(student_id: str) -> list[AccountOperation]:
    """Списания ученика (только `kind='lesson'`), от старых к новым."""
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(AccountOperation)
                .where(
                    AccountOperation.student_id == student_id,
                    AccountOperation.kind == "lesson",
                )
                .order_by(AccountOperation.occurred_at)
            ).all()
        )


def _insert_series(
    tutor_id: str, student_id: str, count: int = 3, **overrides
) -> tuple[str, list[str]]:
    """Серия уроков напрямую в БД: (series_id, id уроков по времени).

    Прямая вставка, а не `create_series`: нужны уроки в заданном статусе
    без списаний, чтобы проверить именно путь правки и удаления.
    """
    with SessionLocal() as session:
        values = {
            "student_id": student_id,
            "type": "individual",
            "duration_min": 60,
            "status": "planned",
        }
        values.update(overrides)
        series = LessonSeries(
            slots=[{"weekday": 0, "start_time": "10:00", "end_time": "11:00"}],
            interval_weeks=1,
            until_date=date(2026, 11, 30),
        )
        session.add(series)
        session.flush()
        start = datetime(2026, 10, 19, 10, 0)
        lessons = [
            Lesson(
                series_id=series.id,
                starts_at=start + timedelta(weeks=offset),
                **values,
            )
            for offset in range(count)
        ]
        session.add_all(lessons)
        session.commit()
        return series.id, [lesson.id for lesson in lessons]


def _update_form(student_id: str, **extra) -> dict:
    """Валидная форма редактирования (понедельник 19.10.2026 10:00)."""
    data = {
        "type": "individual",
        "student_id": student_id,
        "starts_at": "2026-10-19T10:00",
        "duration_min": "60",
        "price": "",
        "note": "",
        "meeting_url": "",
    }
    data.update(extra)
    return data


def _mark_completed(client, student_id: str, lesson_id: str, price: str = "1200", **extra):
    """Проводит урок через форму: списание создаёт путь правки (задача 5.4)."""
    return client.post(
        f"/tutor/lessons/{lesson_id}",
        data=_update_form(student_id, price=price, status="completed", **extra),
        headers=HTMX,
    )


# --------------------------------------------------------------------------
# 5.3 Создание
# --------------------------------------------------------------------------


def test_create_completed_lesson_creates_charge(owner, student_factory):
    """Проведённый урок, созданный сервисом, сразу списывает деньги.

    Поля «Проведение» в форме создания нет (созданный урок всегда
    «Запланирован»), поэтому статус задаётся явно на уровне сервиса —
    этим путём пользуются тесты и будущие импорты.
    """
    student_id = student_factory(tutor_id=owner)

    with SessionLocal() as session:
        lesson, errors = create_single_lesson(
            session,
            _lesson_data(student_id, 1200, status="completed"),
            _tutor(session, owner),
        )

    assert errors == []
    charges = _charges(student_id)
    assert len(charges) == 1
    assert charges[0].amount == 1200
    assert charges[0].lesson_id == lesson.id
    with SessionLocal() as session:
        assert balance(session, student_id) == -1200


def test_create_planned_lesson_creates_no_charge(owner, student_factory):
    """Обычное создание через форму даёт «Запланирован» и без списания."""
    student_id = student_factory(tutor_id=owner)

    with SessionLocal() as session:
        lesson, errors = create_single_lesson(
            session, _lesson_data(student_id, 1200), _tutor(session, owner)
        )

    assert errors == []
    assert lesson.status == "planned"
    assert _charges(student_id) == []


def test_create_series_with_completed_lessons_charges_each(owner, student_factory):
    """Серия проведённых уроков списывает по строке на каждый урок."""
    student_id = student_factory(tutor_id=owner)

    with SessionLocal() as session:
        lessons, errors = create_series(
            session,
            _lesson_data(
                student_id,
                1000,
                status="completed",
                repeat=True,
                slots=[{"weekday": 0, "start_time": "10:00", "end_time": "11:00"}],
                interval_weeks=1,
                until_date=date(2026, 11, 2),
            ),
            _tutor(session, owner),
        )

    assert errors == []
    assert len(lessons) == 3
    charges = _charges(student_id)
    assert len(charges) == 3
    assert {charge.lesson_id for charge in charges} == {lesson.id for lesson in lessons}
    with SessionLocal() as session:
        assert balance(session, student_id) == -3000


# --------------------------------------------------------------------------
# 5.4 Правка и массовая правка серии
# --------------------------------------------------------------------------


def test_edit_completed_lesson_price_recalculates_charge(owner, client, student_factory):
    """Правка оплаты проведённого урока пересчитывает его списание."""
    student_id = student_factory(tutor_id=owner)
    lesson = _create_completed_lesson(owner, student_id, price=1200)

    response = client.post(
        f"/tutor/lessons/{lesson.id}",
        data=_update_form(student_id, price="1500", status="completed"),
        headers=HTMX,
    )
    assert response.status_code == 200

    charges = _charges(student_id)
    assert len(charges) == 1
    assert charges[0].amount == 1500


def test_edit_planned_lesson_to_completed_creates_charge(owner, client, student_factory):
    """«Запланирован» → «Проведён» создаёт списание при сохранении."""
    student_id = student_factory(tutor_id=owner)
    _, lesson_ids = _insert_series(owner, student_id, count=1, price=1200)
    assert _charges(student_id) == []

    response = _mark_completed(client, student_id, lesson_ids[0], price="1200")

    assert response.status_code == 200
    charges = _charges(student_id)
    assert len(charges) == 1
    assert charges[0].lesson_id == lesson_ids[0]
    assert charges[0].amount == 1200


def test_edit_completed_lesson_back_to_planned_removes_charge(
    owner, client, student_factory
):
    """«Проведён» → «Запланирован» снимает списание и возвращает баланс."""
    student_id = student_factory(tutor_id=owner)
    _, lesson_ids = _insert_series(owner, student_id, count=1, price=1200)
    # Списание создаёт путь правки: прямой вставкой его не получить.
    _mark_completed(client, student_id, lesson_ids[0])
    assert len(_charges(student_id)) == 1

    response = client.post(
        f"/tutor/lessons/{lesson_ids[0]}",
        data=_update_form(student_id, price="1200", status="planned"),
        headers=HTMX,
    )
    assert response.status_code == 200

    assert _charges(student_id) == []
    with SessionLocal() as session:
        assert balance(session, student_id) == 0


def test_edit_apply_to_series_keeps_charge_of_completed_lesson(
    owner, client, student_factory
):
    """Массовая правка цены меняет списание проведённого урока серии.

    Статус — пер-уточное поле (спека lesson-management), поэтому остальные
    уроки остаются «Запланированными» и списаний не получают: проверяется,
    что пересчёт не создаёт строк там, где занятие не состоялось.
    """
    student_id = student_factory(tutor_id=owner)
    _, lesson_ids = _insert_series(owner, student_id, count=3, price=1200)
    _mark_completed(client, student_id, lesson_ids[0])
    assert len(_charges(student_id)) == 1

    response = client.post(
        f"/tutor/lessons/{lesson_ids[0]}",
        data=_update_form(student_id, price="1500", status="completed", series_all="1"),
        headers=HTMX,
    )
    assert response.status_code == 200

    charges = _charges(student_id)
    assert [charge.amount for charge in charges] == [1500]
    assert [charge.lesson_id for charge in charges] == [lesson_ids[0]]


def test_edit_apply_to_series_recalculates_every_completed_lesson(
    owner, client, student_factory
):
    """Если проведены все уроки серии, массовая правка меняет все списания."""
    student_id = student_factory(tutor_id=owner)
    _, lesson_ids = _insert_series(
        owner, student_id, count=3, price=1200, status="completed"
    )
    # Синхронизируем списания всех уроков: правка каждого по очереди.
    for lesson_id in lesson_ids:
        _mark_completed(client, student_id, lesson_id)
    assert len(_charges(student_id)) == 3

    client.post(
        f"/tutor/lessons/{lesson_ids[1]}",
        data=_update_form(student_id, price="1500", status="completed", series_all="1"),
        headers=HTMX,
    )

    charges = _charges(student_id)
    assert len(charges) == 3
    assert {charge.amount for charge in charges} == {1500}
    with SessionLocal() as session:
        assert balance(session, student_id) == -4500


# --------------------------------------------------------------------------
# 5.5 Удаление
# --------------------------------------------------------------------------


def test_delete_lesson_removes_its_charge(owner, client, student_factory):
    """Удаление урока снимает списание каскадом `lesson_id`."""
    student_id = student_factory(tutor_id=owner)
    lesson = _create_completed_lesson(owner, student_id)
    assert len(_charges(student_id)) == 1

    response = client.post(f"/tutor/lessons/{lesson.id}/delete", headers=HTMX)

    assert response.status_code == 200
    assert _charges(student_id) == []
    with SessionLocal() as session:
        assert balance(session, student_id) == 0


def test_delete_series_removes_all_charges(owner, client, student_factory):
    """Удаление серии снимает списания всех её уроков."""
    student_id = student_factory(tutor_id=owner)
    _, lesson_ids = _insert_series(
        owner, student_id, count=3, price=1000, status="completed"
    )
    for lesson_id in lesson_ids:
        _mark_completed(client, student_id, lesson_id, price="1000")
    assert len(_charges(student_id)) == 3

    response = client.post(
        f"/tutor/lessons/{lesson_ids[0]}/delete-series", headers=HTMX
    )

    assert response.status_code == 200
    assert _charges(student_id) == []
    with SessionLocal() as session:
        assert balance(session, student_id) == 0
