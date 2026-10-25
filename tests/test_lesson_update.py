"""Редактирование, серия и удаление урока (6.1–6.3).

Проверяются HTTP-путём: GET модалки (заголовок, поля, предупреждение,
кнопки), POST сохранения (статус/оценка — пер-уточные, общие поля —
по переключателю серии) и удаление с двухшаговым подтверждением.
"""

import re
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_series import LessonSeries
from app.student.models.student import Student

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="lessons-update@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "lessons-update@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _insert_lesson(tutor_id: str, **overrides) -> str:
    """Урок напрямую в БД; возвращает id (как в test_lesson_pages)."""
    with SessionLocal() as db:
        if "student_id" not in overrides:
            student = db.query(Student).filter_by(tutor_id=tutor_id).first()
            overrides["student_id"] = student.id if student else None
        overrides.setdefault("type", "individual")
        overrides.setdefault("starts_at", datetime(2026, 10, 19, 10, 0))
        overrides.setdefault("duration_min", 60)
        overrides.setdefault("status", "planned")
        lesson = Lesson(**overrides)
        db.add(lesson)
        db.commit()
        return str(lesson.id)


def _insert_series(tutor_id: str, count: int = 3, **overrides) -> tuple[str, list[str]]:
    """Серия уроков напрямую в БД: (series_id, [id уроков по времени])."""
    with SessionLocal() as db:
        student = db.query(Student).filter_by(tutor_id=tutor_id).first()
        overrides.setdefault("student_id", student.id if student else None)
        overrides.setdefault("type", "individual")
        overrides.setdefault("duration_min", 60)
        overrides.setdefault("status", "planned")
        series = LessonSeries(
            slots=[{"weekday": 0, "start_time": "10:00", "end_time": "11:00"}],
            interval_weeks=1,
            until_date=date(2026, 11, 30),
        )
        db.add(series)
        db.flush()
        start = datetime(2026, 10, 19, 10, 0)
        lessons = [
            Lesson(
                series_id=series.id,
                starts_at=start + timedelta(weeks=offset),
                **overrides,
            )
            for offset in range(count)
        ]
        db.add_all(lessons)
        db.commit()
        return series.id, [str(lesson.id) for lesson in lessons]


def _lesson(lesson_id: str) -> dict:
    """Снимок одного урока."""
    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        return {
            "student_id": lesson.student_id,
            "type": lesson.type,
            "starts_at": lesson.starts_at,
            "duration_min": lesson.duration_min,
            "note": lesson.note,
            "meeting_url": lesson.meeting_url,
            "price": lesson.price,
            "status": lesson.status,
            "rating": lesson.rating,
            "family_comment": lesson.family_comment,
            "series_id": lesson.series_id,
        }


def _exists(model, entity_id: str) -> bool:
    with SessionLocal() as db:
        return db.get(model, entity_id) is not None


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


def _owner_utc_plus4(client, tutor_factory):
    """Репетитор с зоной Europe/Ulyanovsk (UTC+04), вошедший в клиент."""
    email = "lessons-update-tz@example.com"
    tutor_id = tutor_factory(
        email=email, password=PASSWORD, timezone="Europe/Ulyanovsk"
    )
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


# --------------------------------------------------------------------------
# 6.1 Модалка редактирования
# --------------------------------------------------------------------------


def test_edit_form_prefills_local_and_saving_keeps_utc(
    client, tutor_factory, student_factory
):
    """Спека (задача 3.2): урок `06:00 UTC` при зоне UTC+04.

    Поле «Начало» показывает настенное время 10:00, а сохранение без
    правки не сдвигает хранимое значение в БД.
    """
    owner = _owner_utc_plus4(client, tutor_factory)
    student = student_factory(tutor_id=owner)
    # Хранимое значение — 06:00 UTC, что в зоне UTC+04 есть 22.10 10:00.
    lesson_id = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 22, 6, 0)
    )

    page = client.get(f"/tutor/lessons/{lesson_id}/edit").text
    assert 'value="2026-10-22T10:00"' in page
    # Подзаголовок модалки — интервал в зоне педагога: 10:00–11:00 (задача 5.1).
    assert "10:00–11:00" in page

    # Сохранение без правки не меняет хранимое UTC-значение.
    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data=_update_form(student, starts_at="2026-10-22T10:00"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert _lesson(lesson_id)["starts_at"] == datetime(2026, 10, 22, 6, 0)


def test_edit_form_renders(owner, client, student_factory):
    """Заголовок «Цель · дата, время», подзаголовок-интервал, поля, кнопки."""
    student = student_factory(tutor_id=owner, first_name="Мария", last_name="Иванова")
    lesson_id = _insert_lesson(
        owner, student_id=student, note="Подготовка", price=1200
    )

    page = client.get(f"/tutor/lessons/{lesson_id}/edit").text

    assert "Мария Иванова · 19.10.2026, 10:00" in page
    assert "10:00–11:00" in page  # подзаголовок-интервал
    assert ">Закрыть</button>" in page
    # Кнопки сохранения — в футере модалки (вне скролла) и меняются вместе
    # с вкладкой: `form=` связывает каждую со своей формой, видимость
    # переключает Alpine по activeTab.
    assert ">Сохранить</button>" in page
    assert 'type="submit" form="lesson-form"' in page
    assert "x-show=\"activeTab === 'lesson'\"" in page
    assert 'type="submit" form="homework-panel"' in page
    assert "data-hw-save" in page
    assert "x-show=\"activeTab === 'hw'\"" in page

    # Поля создания + статус + блок «Для семьи».
    for marker in (
        'name="note"',
        'name="meeting_url"',
        'name="starts_at"',
        'name="duration_min"',
        'name="type"',
        'name="price"',
        'name="status"',
        'name="rating"',
        'name="family_comment"',
    ):
        assert marker in page, marker
    assert "Для семьи" in page
    assert "Запланирован" in page
    assert "Проведён" in page

    # Серия в редактировании полем не управляется (решение: генерация
    # только при создании), у одиночного урока нет переключателя и «Серию».
    assert 'name="repeat"' not in page
    assert 'name="series_all"' not in page
    assert "Серию" not in page
    # Удаление урока — иконка-кнопка с aria-label; confirm-шаг — словами.
    assert 'aria-label="Удалить урок"' in page
    assert "Точно удалить?" in page
    # Вкладка «ДЗ» в редактировании активна: без disabled, переключение
    # Alpine по activeTab, панель ДЗ присутствует (спека lesson-management).
    hw_tab = re.search(r'<button class="tab"[^>]*id="lesson-tab-hw"[^>]*>', page)
    assert hw_tab is not None
    assert "disabled" not in hw_tab.group(0)
    assert ':aria-selected="activeTab === \'hw\' ? \'true\' : \'false\'"' in hw_tab.group(0)
    assert '@click="activeTab = \'hw\'"' in hw_tab.group(0)
    assert 'id="lesson-panel-hw"' in page
    assert 'x-show="activeTab === \'hw\'"' in page
    # Панель ДЗ — отдельная форма со своими полями и кнопкой.
    assert 'name="assignment"' in page
    assert re.search(r">\s*Сохранить ДЗ\s*</button>", page)
    assert 'hx-post="/tutor/lessons/%s/homework"' % lesson_id in page
    # Футер (группа удаления, «Закрыть», кнопки сохранения) — после
    # закрытия обеих форм: он общий и не скролится с телом модалки.
    assert re.search(
        r"</form>\s*</div>\s*</div>\s*<div class=\"modal-actions\">", page
    )


def test_list_row_opens_edit_modal(owner, client, student_factory):
    """Строка списка открывает модалку редактирования (HTMX-запрос строки)."""
    student = student_factory(tutor_id=owner)
    lesson_id = _insert_lesson(owner, student_id=student)
    page = client.get("/tutor/lessons").text
    row = re.search(
        rf'<tr class="lessons-table__row" id="lesson-row-{re.escape(lesson_id)}[^>]*>',
        page,
    )
    assert row is not None
    assert f'hx-get="/tutor/lessons/{lesson_id}/edit"' in row.group(0)


def test_edit_requires_session(client, tutor_factory, student_factory):
    """Без входа модалка и сохранение недоступны — редирект на вход."""
    tutor_id = tutor_factory(email="lessons-update-guest@example.com")
    student = student_factory(tutor_id=tutor_id)
    lesson_id = _insert_lesson(tutor_id, student_id=student)

    response = client.get(
        f"/tutor/lessons/{lesson_id}/edit", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"

    response = client.post(
        f"/tutor/lessons/{lesson_id}", follow_redirects=False
    )
    assert response.status_code == 303
    assert _lesson(lesson_id)["status"] == "planned"


def test_edit_status_and_rating(owner, client, student_factory):
    """Проведённый урок: статус, оценка, комментарий; список — «(Оплачено)»."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    lesson_id = _insert_lesson(owner, student_id=student, price=1200)

    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data=_update_form(
            student,
            status="completed",
            rating="5",
            family_comment="Отлично поняла тему",
            price="1200",
        ),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "lesson-saved"

    saved = _lesson(lesson_id)
    assert saved["status"] == "completed"
    assert saved["rating"] == 5
    assert saved["family_comment"] == "Отлично поняла тему"

    page = client.get("/tutor/lessons").text
    row = re.search(
        rf'<tr class="lessons-table__row" id="lesson-row-{re.escape(lesson_id)}[^>]*>.*?</tr>',
        page,
        re.S,
    ).group(0)
    assert "Проведён" in row
    assert "1\u00a0200\u00a0₽ (Оплачено)" in row
    assert "★★★★★" in row


def test_edit_rating_must_be_1_to_5(owner, client, student_factory):
    """Оценка вне 1–5 блокирует сохранение и не меняет урок."""
    student = student_factory(tutor_id=owner)
    lesson_id = _insert_lesson(owner, student_id=student, rating=3)

    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data=_update_form(student, rating="9"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert "Оценка — от 1 до 5 звёзд." in response.text
    assert _lesson(lesson_id)["rating"] == 3


def test_edit_price_readonly_for_completed(owner, client, student_factory):
    """Оплата проведённого урока видна, но не редактируется; у запланированного — редактируется."""
    student = student_factory(tutor_id=owner)
    done = _insert_lesson(
        owner, student_id=student, status="completed", price=1200
    )
    planned = _insert_lesson(
        owner,
        student_id=student,
        starts_at=datetime(2026, 10, 20, 10, 0),
        price=1200,
    )

    page = client.get(f"/tutor/lessons/{done}/edit").text
    assert re.search(r'id="lesson-price"[^>]*readonly', page)
    assert "Урок проведён: оплата не изменяется." in page
    assert "пересчитает списание" not in page

    page = client.get(f"/tutor/lessons/{planned}/edit").text
    assert not re.search(r'id="lesson-price"[^>]*readonly', page)
    assert "оплата не изменяется" not in page


def test_edit_completed_lesson_ignores_submitted_price(
    owner, client, student_factory
):
    """Сервер игнорирует оплату проведённого урока: цена в БД не меняется.

    Поле readonly в форме не защита — прямым POST цену тоже не изменить
    (спека «Цена проведённого урока только для чтения»).
    """
    student = student_factory(tutor_id=owner)
    lesson_id = _insert_lesson(
        owner, student_id=student, status="completed", price=1200
    )

    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data=_update_form(student, status="completed", price="9999"),
        headers=HTMX,
    )
    assert response.status_code == 200
    assert _lesson(lesson_id)["price"] == 1200


def test_edit_foreign_lesson_is_missing(
    owner, client, tutor_factory, student_factory, group_factory
):
    """Чужой урок недоступен: форма, сохранение и удаление отвечают 404."""
    other = tutor_factory(email="lessons-update-other@example.com")
    foreign_student = student_factory(tutor_id=other)
    foreign = _insert_lesson(other, student_id=foreign_student)

    group = group_factory(tutor_id=other)
    foreign_group = _insert_lesson(
        other, student_id=None, group_id=group, type="group"
    )

    assert client.get(f"/tutor/lessons/{foreign}/edit").status_code == 404
    assert client.post(
        f"/tutor/lessons/{foreign}",
        data=_update_form(foreign_student),
        headers=HTMX,
    ).status_code == 404
    assert client.post(
        f"/tutor/lessons/{foreign}/delete", headers=HTMX
    ).status_code == 404
    assert client.post(
        f"/tutor/lessons/{foreign_group}/delete", headers=HTMX
    ).status_code == 404

    # Уроки не изменились и не удалились.
    assert _exists(Lesson, foreign)
    assert _exists(Lesson, foreign_group)


# --------------------------------------------------------------------------
# 6.2 Переключатель «Применить ко всей серии»
# --------------------------------------------------------------------------


def test_series_member_form_has_series_toggle(owner, client, student_factory):
    """Переключатель «Применить ко всей серии» — только у члена серии."""
    student = student_factory(tutor_id=owner)
    _, lesson_ids = _insert_series(owner, student_id=student, count=2)

    page = client.get(f"/tutor/lessons/{lesson_ids[0]}/edit").text
    assert 'name="series_all"' in page
    assert "Применить ко всей серии" in page


def test_edit_single_lesson_of_series_without_toggle(owner, client, student_factory):
    """Без переключателя правка применяется только к этому уроку."""
    student = student_factory(tutor_id=owner)
    _, lesson_ids = _insert_series(
        owner, student_id=student, count=3, note="Старая заметка"
    )

    response = client.post(
        f"/tutor/lessons/{lesson_ids[1]}",
        data=_update_form(student, note="Перенесли домашку"),
        headers=HTMX,
    )
    assert response.status_code == 200

    assert _lesson(lesson_ids[1])["note"] == "Перенесли домашку"
    assert _lesson(lesson_ids[0])["note"] == "Старая заметка"
    assert _lesson(lesson_ids[2])["note"] == "Старая заметка"


def test_edit_apply_to_series_updates_common_fields(owner, client, student_factory):
    """Общие поля уходят на всю серию (включая прошедшие уроки)."""
    student = student_factory(tutor_id=owner)
    _, lesson_ids = _insert_series(owner, student_id=student, count=3)

    response = client.post(
        f"/tutor/lessons/{lesson_ids[2]}",
        data=_update_form(student, type="trial", duration_min="90", series_all="1"),
        headers=HTMX,
    )
    assert response.status_code == 200

    for lesson_id in lesson_ids:
        saved = _lesson(lesson_id)
        assert saved["type"] == "trial"
        assert saved["duration_min"] == 90


def test_edit_series_rating_stays_per_lesson(owner, client, student_factory):
    """С включённым переключателем оценка/статус/заметка — только у урока."""
    student = student_factory(tutor_id=owner)
    _, lesson_ids = _insert_series(owner, student_id=student, count=2)

    response = client.post(
        f"/tutor/lessons/{lesson_ids[0]}",
        data=_update_form(
            student,
            series_all="1",
            status="completed",
            rating="4",
            family_comment="Хорошо",
            note="Только этот урок",
            duration_min="90",
        ),
        headers=HTMX,
    )
    assert response.status_code == 200

    edited = _lesson(lesson_ids[0])
    assert edited["status"] == "completed"
    assert edited["rating"] == 4
    assert edited["family_comment"] == "Хорошо"
    assert edited["note"] == "Только этот урок"
    assert edited["duration_min"] == 90  # общее поле — на уроке тоже

    other = _lesson(lesson_ids[1])
    assert other["status"] == "planned"
    assert other["rating"] is None
    assert other["family_comment"] is None
    assert other["note"] is None
    assert other["duration_min"] == 90  # общее поле применилось и к нему


# --------------------------------------------------------------------------
# 6.3 Удаление урока и серии
# --------------------------------------------------------------------------


def test_delete_single_lesson(owner, client, student_factory):
    """«Удалить»: урок исчез, окно закрывается событием, список обновляется."""
    student = student_factory(tutor_id=owner)
    keep = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 20, 10, 0)
    )
    doomed = _insert_lesson(owner, student_id=student)

    response = client.post(
        f"/tutor/lessons/{doomed}/delete", headers=HTMX
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "lesson-saved"

    assert not _exists(Lesson, doomed)
    assert _exists(Lesson, keep)

    page = client.get("/tutor/lessons").text
    assert f"lesson-row-{doomed}" not in page
    assert f"lesson-row-{keep}" in page


def test_delete_single_lesson_without_htmx_redirects(owner, client, student_factory):
    """Прямая POST-навигация без htmx — редиректом на список."""
    student = student_factory(tutor_id=owner)
    doomed = _insert_lesson(owner, student_id=student)

    response = client.post(
        f"/tutor/lessons/{doomed}/delete", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/lessons"
    assert not _exists(Lesson, doomed)


def test_delete_one_member_keeps_series(owner, client, student_factory):
    """Удаление одного урока серии не трогает остальные уроки и серию."""
    student = student_factory(tutor_id=owner)
    series_id, lesson_ids = _insert_series(owner, student_id=student, count=3)

    response = client.post(
        f"/tutor/lessons/{lesson_ids[0]}/delete", headers=HTMX
    )
    assert response.status_code == 200

    assert not _exists(Lesson, lesson_ids[0])
    assert _exists(Lesson, lesson_ids[1])
    assert _exists(Lesson, lesson_ids[2])
    assert _exists(LessonSeries, series_id)


def test_delete_series(owner, client, student_factory):
    """«Серию»: удаляются все уроки серии и сама серия."""
    student = student_factory(tutor_id=owner)
    single = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 12, 1, 10, 0)
    )
    series_id, lesson_ids = _insert_series(owner, student_id=student, count=3)

    response = client.post(
        f"/tutor/lessons/{lesson_ids[1]}/delete-series", headers=HTMX
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "lesson-saved"

    for lesson_id in lesson_ids:
        assert not _exists(Lesson, lesson_id)
    assert not _exists(LessonSeries, series_id)
    assert _exists(Lesson, single)  # одиночный урок не пострадал


def test_delete_series_button_only_for_members(owner, client, student_factory):
    """Кнопка «Серию» есть у члена серии и отсутствует у одиночного урока."""
    student = student_factory(tutor_id=owner)
    single = _insert_lesson(owner, student_id=student)
    _, lesson_ids = _insert_series(owner, student_id=student, count=2)

    single_form = client.get(f"/tutor/lessons/{single}/edit").text
    assert "Серию" not in single_form

    member_form = client.get(f"/tutor/lessons/{lesson_ids[0]}/edit").text
    assert "Серию" in member_form


def test_delete_series_of_single_lesson_404(owner, client, student_factory):
    """POST «Серию» для одиночного урока отвечает как несуществующая серия."""
    student = student_factory(tutor_id=owner)
    single = _insert_lesson(owner, student_id=student)

    response = client.post(
        f"/tutor/lessons/{single}/delete-series", headers=HTMX
    )
    assert response.status_code == 404
    assert _exists(Lesson, single)


# --------------------------------------------------------------------------
# Перенос урока перетаскиванием (change calendar-real-lessons, 5.1–5.2)
# --------------------------------------------------------------------------

def test_move_lesson_changes_only_starts_at(owner, client, student_factory):
    """5.1: успешный перенос меняет только начало и шлёт `lesson-saved`."""
    student = student_factory(tutor_id=owner)
    lesson_id = _insert_lesson(
        owner, student_id=student, note="Не трогать",
        starts_at=datetime(2026, 10, 19, 10, 0),
    )
    before = _lesson(lesson_id)

    response = client.post(
        f"/tutor/lessons/{lesson_id}/move",
        data={"date": "2026-10-23", "time": "16:30"},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "lesson-saved"
    assert response.text == ""  # пустое тело — неделя перерисовывается

    after = _lesson(lesson_id)
    assert after["starts_at"] == datetime(2026, 10, 23, 16, 30)
    # Остальные поля урока не изменились: drag трогает только начало.
    for field in (
        "student_id", "type", "duration_min", "note", "meeting_url",
        "price", "status", "rating", "family_comment", "series_id",
    ):
        assert after[field] == before[field], field


def test_move_lesson_in_tutor_zone_saves_utc(
    client, tutor_factory, student_factory
):
    """Спека (задача 5.3): перенос 16:30 при зоне UTC+04 сохраняет 12:30 UTC.

    Переданные дата и время трактуются как настенное время в зоне педагога.
    """
    owner = _owner_utc_plus4(client, tutor_factory)
    student = student_factory(tutor_id=owner)
    lesson_id = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 6, 0)
    )

    response = client.post(
        f"/tutor/lessons/{lesson_id}/move",
        data={"date": "2026-10-23", "time": "16:30"},
        headers=HTMX,
    )
    assert response.status_code == 200

    # 16:30 в UTC+04 — это 12:30 UTC того же дня.
    assert _lesson(lesson_id)["starts_at"] == datetime(2026, 10, 23, 12, 30)

    # Календарь показывает урок в настенном времени педагога: 16:30, а не 12:30
    # (спека tutor-timezone, «Показ времени урока»).
    calendar = client.get("/tutor/calendar?start=2026-10-19").text
    assert 'hx-get="/tutor/lessons/' + lesson_id in calendar
    assert "16:30 – 17:30" in calendar


def test_move_lesson_without_htmx_redirects(owner, client, student_factory):
    """5.1: прямая POST-навигация без htmx уводит на календарь."""
    student = student_factory(tutor_id=owner)
    lesson_id = _insert_lesson(owner, student_id=student)

    response = client.post(
        f"/tutor/lessons/{lesson_id}/move",
        data={"date": "2026-10-23", "time": "16:30"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/calendar"
    assert _lesson(lesson_id)["starts_at"] == datetime(2026, 10, 23, 16, 30)


def test_move_foreign_lesson_is_missing(owner, client, tutor_factory, student_factory):
    """5.1: чужой урок отвечает как несуществующий (404), время не меняется."""
    stranger = tutor_factory(email="move-stranger@example.com")
    foreign_student = student_factory(tutor_id=stranger)
    foreign_lesson = _insert_lesson(stranger, student_id=foreign_student)
    before = _lesson(foreign_lesson)["starts_at"]

    response = client.post(
        f"/tutor/lessons/{foreign_lesson}/move",
        data={"date": "2026-10-23", "time": "16:30"},
        headers=HTMX,
    )
    assert response.status_code == 404
    assert _lesson(foreign_lesson)["starts_at"] == before


def test_move_completed_lesson_is_rejected(owner, client, student_factory):
    """5.1: проведённый урок переносить нельзя — 409, время не меняется."""
    student = student_factory(tutor_id=owner)
    lesson_id = _insert_lesson(
        owner, student_id=student, status="completed",
        starts_at=datetime(2026, 10, 19, 10, 0),
    )

    response = client.post(
        f"/tutor/lessons/{lesson_id}/move",
        data={"date": "2026-10-23", "time": "16:30"},
        headers=HTMX,
    )
    assert response.status_code == 409
    assert _lesson(lesson_id)["starts_at"] == datetime(2026, 10, 19, 10, 0)


def test_move_lesson_with_bad_datetime_is_rejected(owner, client, student_factory):
    """5.1: кривые дата/время — 400, урок остаётся на месте."""
    student = student_factory(tutor_id=owner)
    lesson_id = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 10, 0)
    )

    for payload in (
        {"date": "banana", "time": "16:30"},
        {"date": "2026-10-23", "time": "25:99"},
        {"date": "", "time": ""},
    ):
        response = client.post(
            f"/tutor/lessons/{lesson_id}/move", data=payload, headers=HTMX
        )
        assert response.status_code == 400, payload
    assert _lesson(lesson_id)["starts_at"] == datetime(2026, 10, 19, 10, 0)


def test_move_lesson_requires_session(client, tutor_factory, student_factory):
    """5.1: без входа перенос не выполняется — редирект на вход."""
    tutor_id = tutor_factory(email="move-anon@example.com")
    student = student_factory(tutor_id=tutor_id)
    lesson_id = _insert_lesson(tutor_id, student_id=student)

    response = client.post(
        f"/tutor/lessons/{lesson_id}/move",
        data={"date": "2026-10-23", "time": "16:30"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert _lesson(lesson_id)["starts_at"] == datetime(2026, 10, 19, 10, 0)


def test_move_route_does_not_shadow_static_lesson_routes(
    owner, client, student_factory, group_factory
):
    """5.2: `/move` не перехватывает статические маршруты модуля lesson.

    `POST /tutor/lessons/{lesson_id}/move` зарегистрирован после
    статических путей; `/students` и `/groups` по-прежнему отвечают своими
    обработчиками (мини-формы цели урока), а не 404/422 от `{lesson_id}`.
    """
    # Мини-форма ученика: свой обработчик, не маршрут с параметром.
    created = client.post(
        "/tutor/lessons/students",
        data={"first_name": "Мини", "last_name": "Ученик"},
        headers=HTMX,
    )
    assert created.status_code == 200
    assert "data-selected" in created.text

    created_group = client.post(
        "/tutor/lessons/groups",
        data={"name": "Мини-группа"},
        headers=HTMX,
    )
    assert created_group.status_code == 200
    assert "data-selected" in created_group.text

    # И сам перенос доступен.
    student = student_factory(tutor_id=owner)
    lesson_id = _insert_lesson(owner, student_id=student)
    moved = client.post(
        f"/tutor/lessons/{lesson_id}/move",
        data={"date": "2026-10-20", "time": "09:15"},
        headers=HTMX,
    )
    assert moved.status_code == 200
    assert moved.headers["HX-Trigger"] == "lesson-saved"
