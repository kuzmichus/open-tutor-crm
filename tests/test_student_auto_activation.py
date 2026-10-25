"""Автоперевод «нового» ученика в «Активные» за первый платный урок.

HTTP-клиент проходит тот же путь, что и браузер: проведение урока — POST
формы редактирования, пересчёт — кнопка на вкладке «Платежи» карточки.
Статус проверяется и в БД (точное значение), и через фильтр списка
учеников («Активные») — страница обязана показать ученика в этом фильтре.
"""

from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.student.models.student import Student

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


def _owner(client, tutor_factory, email="auto-act@example.com") -> str:
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email=email, password=PASSWORD)
    client.post("/tutor/login", data={"email": email, "password": PASSWORD})
    return tutor_id


def _status(student_id: str) -> str:
    with SessionLocal() as db:
        return db.get(Student, student_id).status


def _charges(student_id: str) -> int:
    """Число списаний за уроки у ученика."""
    with SessionLocal() as db:
        return len(
            db.scalars(
                select(AccountOperation.id).where(
                    AccountOperation.student_id == student_id,
                    AccountOperation.kind == "lesson",
                )
            ).all()
        )


def _update_form(student_id: str, **extra) -> dict:
    """Валидная форма редактирования урока (понедельник 19.10.2026 10:00)."""
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


def test_first_paid_lesson_activates(
    client, tutor_factory, student_factory, lesson_factory
):
    """Проведение индивидуального урока с ценой переводит «нового» в активные."""
    owner = _owner(client, tutor_factory)
    student = student_factory(tutor_id=owner)  # статус по умолчанию — «новый»
    lesson = lesson_factory(student_id=student, status="planned", price=None)

    response = client.post(
        f"/tutor/lessons/{lesson}",
        data=_update_form(student, status="completed", price="1200"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert _status(student) == "active"
    assert _charges(student) == 1

    # Страница показывает ученика в фильтре «Активные».
    listed = client.get("/tutor/students", params={"status": "active"})
    assert "active" in listed.text  # фильтр применён
    with SessionLocal() as db:
        name = db.get(Student, student).first_name
    assert name in listed.text


def test_group_lesson_activates_members(
    client, tutor_factory, student_factory, group_factory, group_member_factory, lesson_factory
):
    """Проведение группового урока активирует участников с определимой ценой."""
    owner = _owner(client, tutor_factory, email="auto-act-group@example.com")
    group = group_factory(tutor_id=owner, price_per_lesson=1500)
    first = student_factory(tutor_id=owner)
    second = student_factory(tutor_id=owner)
    group_member_factory(group_id=group, student_id=first)
    group_member_factory(group_id=group, student_id=second)
    lesson = lesson_factory(group_id=group, status="planned", price=None)

    response = client.post(
        f"/tutor/lessons/{lesson}",
        data=_update_form("", type="group", group_id=group, status="completed"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert _status(first) == "active"
    assert _status(second) == "active"
    assert _charges(first) == 1
    assert _charges(second) == 1


def test_free_lesson_does_not_activate(
    client, tutor_factory, student_factory, lesson_factory
):
    """Проведённый урок без цены — списания нет, статус остаётся «новый»."""
    owner = _owner(client, tutor_factory, email="auto-act-free@example.com")
    student = student_factory(tutor_id=owner)
    lesson = lesson_factory(student_id=student, status="planned", price=None)

    response = client.post(
        f"/tutor/lessons/{lesson}",
        data=_update_form(student, status="completed"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert _status(student) == "new"
    assert _charges(student) == 0


def test_revert_to_planned_keeps_active(
    client, tutor_factory, student_factory, lesson_factory
):
    """Возврат урока в «Запланирован» снимает списание, но не статус.

    Активация — одностороннее правило: факт «урок состоялся и был
    оплачен» не переписывается задним числом.
    """
    owner = _owner(client, tutor_factory, email="auto-act-revert@example.com")
    student = student_factory(tutor_id=owner)
    lesson = lesson_factory(student_id=student, status="planned", price=None)

    client.post(
        f"/tutor/lessons/{lesson}",
        data=_update_form(student, status="completed", price="1200"),
        headers=HTMX,
    )
    client.post(
        f"/tutor/lessons/{lesson}",
        data=_update_form(student, status="planned", price="1200"),
        headers=HTMX,
    )
    assert _status(student) == "active"
    assert _charges(student) == 0


def test_recalculate_activates(
    client, tutor_factory, student_factory, lesson_factory
):
    """«Пересчитать баланс» активирует «нового» с проведёнными уроками.

    Урок создан фабрикой напрямую — списаний фабрика не делает
    (design D6 спеки student-finance), их добавит кнопка пересчёта.
    """
    owner = _owner(client, tutor_factory, email="auto-act-recalc@example.com")
    student = student_factory(tutor_id=owner)
    lesson_factory(student_id=student, status="completed", price=1200)
    assert _status(student) == "new"

    response = client.post(
        f"/tutor/students/{student}/balance/recalculate",
        headers=HTMX,
    )
    assert response.status_code == 200
    assert _status(student) == "active"
    assert _charges(student) == 1


def test_archived_stays_archived(
    client, tutor_factory, student_factory, lesson_factory
):
    """Списание у архивного ученика не возвращает его в «Активные»."""
    owner = _owner(client, tutor_factory, email="auto-act-archive@example.com")
    student = student_factory(tutor_id=owner, status="archived")
    lesson = lesson_factory(student_id=student, status="planned", price=None)

    response = client.post(
        f"/tutor/lessons/{lesson}",
        data=_update_form(student, status="completed", price="1200"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert _status(student) == "archived"
    assert _charges(student) == 1  # списание создано, статус не тронут


def test_active_stays_active(
    client, tutor_factory, student_factory, lesson_factory
):
    """Повторное проведение урока у «активного» ничего не меняет и не падает."""
    owner = _owner(client, tutor_factory, email="auto-act-twice@example.com")
    student = student_factory(tutor_id=owner, status="active")
    lesson = lesson_factory(student_id=student, status="planned", price=None)

    response = client.post(
        f"/tutor/lessons/{lesson}",
        data=_update_form(student, status="completed", price="1200"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert _status(student) == "active"
    assert _charges(student) == 1
