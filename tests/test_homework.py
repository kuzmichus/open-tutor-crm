"""Тесты модуля homework: модель, форма, сохранение, панель и изоляция."""

import re
from contextlib import contextmanager
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.homework.models.homework import (
    HOMEWORK_STATUS_LABELS,
    HOMEWORK_STATUSES,
    Homework,
)
from app.homework.services.homework_form import parse_homework_form
from app.homework.services.homework_writer import get_homework, save_homework
from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_series import LessonSeries

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}

# Карточка репетитора для разбора формы: сервисам нужен только её зона.
# UTC — тесты не зависят от системной зоны машины (спека tutor-timezone).
UTC_TUTOR = SimpleNamespace(timezone="UTC")


@contextmanager
def _expect_integrity_error():
    """Контекст: `session.commit()` обязан упасть с IntegrityError.

    Используется для проверок CHECK-ограничений: запись с недопустимым
    значением не должна сохраниться.
    """
    with SessionLocal() as session:
        yield session
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return
    raise AssertionError("ожидался IntegrityError, но запись сохранилась")


@pytest.fixture()
def lesson_id(tutor_factory, student_factory):
    """Одиночный урок в тестовой БД; возвращает его id."""
    tutor_id = tutor_factory(email="homework@example.com")
    student = student_factory(tutor_id=tutor_id)
    with SessionLocal() as db:
        lesson = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(lesson)
        db.commit()
        return str(lesson.id)


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="homework-ui@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "homework-ui@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def owner_lesson(owner, student_factory):
    """Урок вошедшего репетитора; возвращает его id."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    with SessionLocal() as db:
        lesson = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(lesson)
        db.commit()
        return str(lesson.id)


def _hw_form(**extra) -> dict:
    """Валидная форма панели ДЗ."""
    data = {
        "assignment": "§ 12, упр. 4",
        "due_at": "2026-10-25T18:00",
        "deadline_enabled": "on",
        "status": "assigned",
        "recording_url": "https://record.example.com/v/1",
        "teacher_note": "Повторить тему",
        "teacher_comment": "Сдал без ошибок",
    }
    data.update(extra)
    return data


# --------------------------------------------------------------------------
# 1.1 Модель Homework
# --------------------------------------------------------------------------


def test_homework_defaults_on_new_row(lesson_id):
    """Новая запись ДЗ: статус по умолчанию «not_assigned», дедлайн включён."""
    with SessionLocal() as db:
        homework = Homework(lesson_id=lesson_id, assignment="§ 12, упр. 4")
        db.add(homework)
        db.commit()
        db.refresh(homework)

        assert homework.status == "not_assigned"
        assert homework.deadline_enabled is True
        assert homework.due_at is None
        assert homework.recording_url is None
        assert homework.teacher_note is None
        assert homework.teacher_comment is None


def test_homework_statuses_match_labels():
    """Пять статусов ДЗ, каждый с русским лейблом; «Не задано» — первый."""
    assert len(HOMEWORK_STATUSES) == 5
    assert set(HOMEWORK_STATUSES) == set(HOMEWORK_STATUS_LABELS)
    assert HOMEWORK_STATUS_LABELS["not_assigned"] == "Не задано"


def test_homework_status_out_of_list_fails_check(lesson_id):
    """Статус вне закрытого списка отклоняется CHECK-ограничением."""
    with _expect_integrity_error() as db:
        db.add(
            Homework(
                lesson_id=lesson_id,
                assignment="Задание",
                status="in_progress",
            )
        )


def test_homework_lesson_id_is_unique(lesson_id):
    """Вторая запись ДЗ на тот же урок невозможна (UNIQUE на lesson_id)."""
    with SessionLocal() as db:
        db.add(Homework(lesson_id=lesson_id, assignment="Первое ДЗ"))
        db.commit()

    with _expect_integrity_error() as db:
        db.add(Homework(lesson_id=lesson_id, assignment="Второе ДЗ"))


# --------------------------------------------------------------------------
# 2.1 Разбор формы (parse_homework_form)
# --------------------------------------------------------------------------


def test_parse_empty_assignment_is_error():
    """Пустое или пробельное «Задание» — ошибка «Укажите задание.»."""
    for raw in ("", "   "):
        data, errors = parse_homework_form({"assignment": raw}, UTC_TUTOR)
        assert "Укажите задание." in errors, raw
        assert data["assignment"] == ""


def test_parse_empty_due_at_is_not_error():
    """Пустой «Срок сдачи» — не ошибка, значение None."""
    data, errors = parse_homework_form(
        {"assignment": "§ 12, упр. 4", "due_at": ""}, UTC_TUTOR
    )
    assert errors == []
    assert data["due_at"] is None


def test_parse_broken_due_at_is_error():
    """Кривая строка срока сдачи — ошибка, значение не сохраняется."""
    data, errors = parse_homework_form(
        {"assignment": "§ 12", "due_at": "позже"}, UTC_TUTOR
    )
    assert "Укажите корректный срок сдачи." in errors
    assert data["due_at"] is None


@pytest.mark.parametrize(
    ("timezone", "expected"),
    [
        ("UTC", datetime(2026, 10, 25, 18, 0, tzinfo=UTC)),
        ("Europe/Ulyanovsk", datetime(2026, 10, 25, 14, 0, tzinfo=UTC)),
    ],
    ids=["utc", "utc-plus4"],
)
def test_parse_due_at_converts_tutor_zone_to_utc(timezone, expected):
    """Срок `datetime-local` хранится в aware UTC по зоне педагога.

    Спека (задача 6.1): 18:00 настенного времени при зоне UTC+04 — это
    14:00 UTC; при зоне UTC настенное время совпадает с UTC-значением.
    """
    data, errors = parse_homework_form(
        {"assignment": "§ 12", "due_at": "2026-10-25T18:00"},
        SimpleNamespace(timezone=timezone),
    )

    assert errors == []
    assert data["due_at"] == expected


def test_parse_status_out_of_list_is_error():
    """Статус вне закрытого списка отклоняется валидацией (спека)."""
    data, errors = parse_homework_form(
        {"assignment": "§ 12", "status": "in_progress"}, UTC_TUTOR
    )
    assert "Выберите статус домашнего задания." in errors
    assert data["status"] == "in_progress"


def test_parse_clears_optional_text_fields():
    """Пустые необязательные поля уходят в данные как None."""
    data, errors = parse_homework_form(
        {
            "assignment": " § 12 ",
            "recording_url": "  ",
            "teacher_note": "",
            "teacher_comment": "",
        },
        UTC_TUTOR,
    )
    assert errors == []
    assert data["assignment"] == "§ 12"
    assert data["recording_url"] is None
    assert data["teacher_note"] is None
    assert data["teacher_comment"] is None


# --------------------------------------------------------------------------
# 2.2 Сохранение (save_homework)
# --------------------------------------------------------------------------


def test_save_homework_creates_then_updates_same_row(lesson_id):
    """Ленивое создание при первом сохранении, повторное — та же строка."""
    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        assert get_homework(db, lesson_id) is None

        assert save_homework(db, lesson, {"assignment": "Первое ДЗ"}) == []
        first = get_homework(db, lesson_id)
        assert first is not None
        assert first.assignment == "Первое ДЗ"
        assert first.status == "not_assigned"  # значение по умолчанию
        first_id = first.id

    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        errors = save_homework(
            db,
            lesson,
            {
                "assignment": "Второе ДЗ",
                "status": "assigned",
                "due_at": datetime(2026, 10, 25, 18, 0),
                "deadline_enabled": True,
                "recording_url": "https://record.example.com/v/1",
                "teacher_note": "Повторить тему",
                "teacher_comment": "Сдал без ошибок",
            },
        )
        assert errors == []

        rows = db.scalars(
            select(Homework).where(Homework.lesson_id == lesson_id)
        ).all()
        assert len(rows) == 1  # UNIQUE на lesson_id: вторая запись не создана
        assert rows[0].id == first_id
        assert rows[0].assignment == "Второе ДЗ"
        assert rows[0].status == "assigned"
        assert rows[0].due_at == datetime(2026, 10, 25, 18, 0)
        assert rows[0].recording_url == "https://record.example.com/v/1"
        assert rows[0].teacher_note == "Повторить тему"
        assert rows[0].teacher_comment == "Сдал без ошибок"


def test_save_homework_error_keeps_existing_row(lesson_id):
    """Ошибка валидации (пустое задание) не меняет существующее ДЗ."""
    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        save_homework(
            db,
            lesson,
            {"assignment": "Сохранённое ДЗ", "status": "assigned"},
        )

    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        errors = save_homework(
            db, lesson, {"assignment": "   ", "status": "checked"}
        )
        assert errors == ["Укажите задание."]

        kept = get_homework(db, lesson_id)
        assert kept.assignment == "Сохранённое ДЗ"
        assert kept.status == "assigned"  # статус из формы тоже не применился


# --------------------------------------------------------------------------
# 2.3 Эндпоинт POST /tutor/lessons/{lesson_id}/homework
# --------------------------------------------------------------------------


def test_save_homework_success_returns_filled_panel(owner, client, owner_lesson):
    """Успех: 200, панель ДЗ с сохранёнными значениями, без HX-Trigger, ДЗ в БД."""
    response = client.post(
        f"/tutor/lessons/{owner_lesson}/homework",
        data=_hw_form(),
        headers=HTMX,
    )
    assert response.status_code == 200
    # Панель возвращается заполненной и без ошибок: outerHTML подменяет
    # её на свежую, вкладка «ДЗ» не становится пустой (design D3).
    assert '<form id="homework-panel"' in response.text
    assert "§ 12, упр. 4" in response.text
    assert 'value="2026-10-25T18:00"' in response.text
    assert "role=\"alert\"" not in response.text
    assert "HX-Trigger" not in response.headers
    # Кнопка в состоянии успеха (design D8): неактивна, зелёная, с новой
    # надписью; lessons.js вернёт её в обычный вид через пару секунд.
    assert "btn--success" in response.text
    assert "disabled" in response.text
    assert "Успешно сохранено" in response.text

    with SessionLocal() as db:
        saved = get_homework(db, owner_lesson)
        assert saved is not None
        assert saved.assignment == "§ 12, упр. 4"
        assert saved.status == "assigned"
        assert saved.due_at == datetime(2026, 10, 25, 18, 0)
        assert saved.deadline_enabled is True


def test_save_homework_error_returns_panel_fragment(owner, client, owner_lesson):
    """Ошибка — фрагмент панели ДЗ с сообщением; записи ДЗ не создаётся."""
    response = client.post(
        f"/tutor/lessons/{owner_lesson}/homework",
        data=_hw_form(assignment=""),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert "Укажите задание." in response.text
    assert '<form id="homework-panel"' in response.text
    # Ошибка — кнопка обычная и активная: повторно отправить можно сразу.
    assert "btn--success" not in response.text
    assert "Успешно сохранено" not in response.text
    assert "Сохранить ДЗ" in response.text
    # Присланные значения возвращены в панель (не потеряны).
    assert 'value="2026-10-25T18:00"' in response.text

    with SessionLocal() as db:
        assert get_homework(db, owner_lesson) is None


def test_save_homework_foreign_lesson_is_404(
    owner, client, tutor_factory, student_factory
):
    """Чужой урок недоступен: система отвечает, как будто урока нет."""
    other = tutor_factory(email="homework-foreign@example.com")
    foreign_student = student_factory(tutor_id=other)
    with SessionLocal() as db:
        foreign = Lesson(
            student_id=foreign_student,
            type="individual",
            starts_at=datetime(2026, 10, 20, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(foreign)
        db.commit()
        foreign_id = str(foreign.id)

    response = client.post(
        f"/tutor/lessons/{foreign_id}/homework",
        data=_hw_form(),
        headers=HTMX,
    )
    assert response.status_code == 404
    with SessionLocal() as db:
        assert get_homework(db, foreign_id) is None


def test_save_homework_requires_session(client, tutor_factory, student_factory):
    """Без сессии — редирект на вход, ДЗ не сохраняется."""
    tutor_id = tutor_factory(email="homework-guest@example.com")
    student = student_factory(tutor_id=tutor_id)
    with SessionLocal() as db:
        lesson = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(lesson)
        db.commit()
        lesson_id_value = str(lesson.id)

    response = client.post(
        f"/tutor/lessons/{lesson_id_value}/homework",
        data=_hw_form(),
        headers=HTMX,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    with SessionLocal() as db:
        assert get_homework(db, lesson_id_value) is None


# --------------------------------------------------------------------------
# 2.4 Панель ДЗ в модалке редактирования (SSR)
# --------------------------------------------------------------------------


def test_homework_panel_renders_all_fields(owner, client, owner_lesson):
    """Панель содержит все поля, подписи, подсказки и кнопку «Сохранить ДЗ»."""
    page = client.get(f"/tutor/lessons/{owner_lesson}/edit").text

    for marker in (
        'name="assignment"',
        'name="due_at"',
        'name="deadline_enabled"',
        'name="status"',
        'name="recording_url"',
        'name="teacher_note"',
        'name="teacher_comment"',
        f'hx-post="/tutor/lessons/{owner_lesson}/homework"',
        'hx-target="#homework-panel"',
        'hx-swap="outerHTML"',
    ):
        assert marker in page, marker

    for text in (
        "Задание *",
        "Срок сдачи",
        "Учитывать дедлайн (напоминания и автоматический статус)",
        "Статус",
        "Файлы",
        "Прикрепить файл",
        "Ссылка на запись урока",
        "Увидит ученик в кабинете",
        "Заметка педагога",
        "Ученику не видна",
        "Комментарий педагога",
    ):
        assert text in page, text

    # Кнопка сохранения ДЗ (с учётом переносов в разметке).
    assert re.search(r">\s*Сохранить ДЗ\s*</button>", page)

    # Чекбокс дедлайна включён по умолчанию; статусы — пять лейблов.
    assert re.search(r'name="deadline_enabled"[^>]*checked', page)
    for label in ("Не задано", "Задано", "Сдано", "Проверено", "Не выполнено"):
        assert label in page, label

    # Файлы — заглушка: у кнопки нет name и она не отправляет данные.
    attach = re.search(r"<button[^>]*>\s*Прикрепить файл\s*</button>", page)
    assert attach is not None
    assert "name=" not in attach.group(0)


# --------------------------------------------------------------------------
# 2.5 Контекст панели: предзаполнение из сохранённого ДЗ
# --------------------------------------------------------------------------


def test_edit_prefills_saved_homework(owner, client, owner_lesson):
    """Сохранённое ДЗ предзаполняет панель, статус выбран, чекбокс по значению."""
    with SessionLocal() as db:
        lesson = db.get(Lesson, owner_lesson)
        assert (
            save_homework(
                db,
                lesson,
                {
                    "assignment": "Сочинение по «Войне и миру»",
                    "due_at": datetime(2026, 11, 1, 23, 59),
                    "deadline_enabled": False,
                    "status": "checked",
                    "recording_url": "https://record.example.com/v/9",
                    "teacher_note": "Только для себя",
                    "teacher_comment": "Отличная работа",
                },
            )
            == []
        )

    page = client.get(f"/tutor/lessons/{owner_lesson}/edit").text

    assert "Сочинение по «Войне и миру»" in page
    assert 'value="2026-11-01T23:59"' in page
    assert 'value="https://record.example.com/v/9"' in page
    assert "Только для себя" in page
    assert "Отличная работа" in page
    # Статус «Проверено» выбран в селекте панели.
    assert re.search(r'<option value="checked"[^>]*selected', page)
    # Чекбокс дедлайна сохранён выключенным.
    assert not re.search(r'name="deadline_enabled"[^>]*checked', page)


# --------------------------------------------------------------------------
# Срок сдачи в зоне педагога (change store-datetimes-in-utc, 6.1–6.2)
# --------------------------------------------------------------------------


@pytest.fixture()
def owner_utc_plus4(client, tutor_factory, student_factory):
    """Репетитор с зоной UTC+04 и его урок; возвращает id урока."""
    tutor_id = tutor_factory(
        email="homework-tz@example.com",
        password=PASSWORD,
        timezone="Europe/Ulyanovsk",
    )
    client.post(
        "/tutor/login",
        data={"email": "homework-tz@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    student = student_factory(tutor_id=tutor_id, first_name="Мария")
    with SessionLocal() as db:
        lesson = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 19, 6, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(lesson)
        db.commit()
        return str(lesson.id)


def _saved_due_at(lesson_id: str):
    """Срок сдачи из БД (naive-формат SQLite: UTC без tzinfo)."""
    with SessionLocal() as db:
        return get_homework(db, lesson_id).due_at


def test_homework_due_at_stored_and_shown_in_tutor_zone(client, owner_utc_plus4):
    """Спека (задача 6.1): ввод 18:00 при зоне UTC+04 → 14:00 в БД.

    При повторном открытии панели поле снова показывает 18:00 — обратный
    перевод на выводе (спека tutor-timezone, «Показ срока сдачи»).
    """
    response = client.post(
        f"/tutor/lessons/{owner_utc_plus4}/homework",
        data=_hw_form(due_at="2026-10-25T18:00"),
        headers=HTMX,
    )
    assert response.status_code == 200

    # 18:00 в UTC+04 — это 14:00 UTC того же дня.
    assert _saved_due_at(owner_utc_plus4) == datetime(2026, 10, 25, 14, 0)

    # Панель показывает настенное время педагога, а не UTC.
    page = client.get(f"/tutor/lessons/{owner_utc_plus4}/edit").text
    assert 'value="2026-10-25T18:00"' in page


def test_homework_resave_without_due_change_keeps_deadline(client, owner_utc_plus4):
    """Спека (задача 6.2): повторное сохранение без правки срока не сдвигает его."""
    client.post(
        f"/tutor/lessons/{owner_utc_plus4}/homework",
        data=_hw_form(due_at="2026-10-25T18:00"),
        headers=HTMX,
    )
    before = _saved_due_at(owner_utc_plus4)

    # Панель прислала то же настенное время — перевода «туда-обратно» быть не должно.
    response = client.post(
        f"/tutor/lessons/{owner_utc_plus4}/homework",
        data=_hw_form(due_at="2026-10-25T18:00"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert _saved_due_at(owner_utc_plus4) == before == datetime(2026, 10, 25, 14, 0)


# --------------------------------------------------------------------------
# 3.3 Каскад: удаление урока и серии уносит ДЗ
# --------------------------------------------------------------------------


def test_delete_lesson_cascades_homework(owner, client, owner_lesson):
    """«Удалить»: урок удалён, его запись ДЗ ушла каскадом."""
    with SessionLocal() as db:
        lesson = db.get(Lesson, owner_lesson)
        assert save_homework(db, lesson, {"assignment": "ДЗ перед удалением"}) == []

    response = client.post(
        f"/tutor/lessons/{owner_lesson}/delete", headers=HTMX
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.get(Lesson, owner_lesson) is None
        assert get_homework(db, owner_lesson) is None
        assert db.scalars(select(Homework)).all() == []  # строк не осталось


def test_delete_series_cascades_homework(owner, client, student_factory):
    """«Серию»: уроки серии удалены, записи ДЗ всех уроков ушли каскадом."""
    student = student_factory(tutor_id=owner)
    with SessionLocal() as db:
        series = LessonSeries(
            slots=[{"weekday": 0, "start_time": "10:00", "end_time": "11:00"}],
            interval_weeks=1,
            until_date=date(2026, 11, 30),
        )
        db.add(series)
        db.flush()
        lessons = [
            Lesson(
                series_id=series.id,
                student_id=student,
                type="individual",
                starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
                duration_min=60,
            )
            for _ in range(2)
        ]
        db.add_all(lessons)
        db.commit()
        lesson_ids = [str(lesson.id) for lesson in lessons]

    with SessionLocal() as db:
        for lesson_id_value in lesson_ids:
            lesson = db.get(Lesson, lesson_id_value)
            assert (
                save_homework(db, lesson, {"assignment": f"ДЗ {lesson_id_value}"})
                == []
            )

    response = client.post(
        f"/tutor/lessons/{lesson_ids[0]}/delete-series", headers=HTMX
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        for lesson_id_value in lesson_ids:
            assert db.get(Lesson, lesson_id_value) is None
        assert db.scalars(select(Homework)).all() == []  # строк не осталось
