"""Вкладка «Занятия» модалки управления группой: список, фильтры, второй слой.

Панель приходит отдельным GET-маршрутом `/tutor/groups/{id}/lessons`
(паттерн панели оплат), поэтому поведение проверяется по этому маршруту
тем же путём, что у пользователя: чипы статуса — параметром `?status=`,
разметка — по тексту строк и htmx-атрибутам.

Клик по занятию открывает модалку урока во втором слое (`#modal-lesson`,
design D10) — как диалоги счёта поверх карточки ученика. htmx шлёт цель
заголовком `HX-Target`, поэтому GET/POST формы урока проверяются с этим
заголовком: повторная отрисовка с ошибкой обязана вернуться во второй
слой, а не вытеснить модалку группы из `#modal`.
"""

from datetime import UTC, datetime

import pytest

from app.database import SessionLocal
from app.homework.models.homework import Homework
from app.lesson.services.group_lessons import normalize_status

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="group-lessons@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "group-lessons@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _lesson(lesson_factory, group_id, *, status="planned", starts_at=None, **extra):
    """Урок группы через фабрику; возвращает id."""
    return lesson_factory(
        group_id=group_id,
        status=status,
        price=None,
        starts_at=starts_at or datetime(2026, 5, 17, 15, 0, tzinfo=UTC),
        **extra,
    )


def _homework(lesson_id: str, *, status="assigned") -> None:
    """Запись ДЗ урока напрямую в БД (ленивое создание — не через HTTP)."""
    with SessionLocal() as db:
        db.add(
            Homework(
                lesson_id=lesson_id,
                assignment="§ 12, упр. 4",
                status=status,
            )
        )
        db.commit()


# --------------------------------------------------------------------------
# Сервис: фильтр статуса
# --------------------------------------------------------------------------


def test_normalize_status_falls_back_to_all():
    """Неизвестное значение query — «Все», а не ошибка."""
    assert normalize_status("") == ""
    assert normalize_status(None) == ""
    assert normalize_status("взлом") == ""
    assert normalize_status("planned") == "planned"
    assert normalize_status("completed") == "completed"


# --------------------------------------------------------------------------
# Панель: список, порядок, индикатор ДЗ
# --------------------------------------------------------------------------


def test_panel_lists_group_lessons_newest_first(
    owner, client, group_factory, lesson_factory
):
    """Занятия группы — новые сверху; чужие уроки в панель не попадают."""
    group_id = group_factory(tutor_id=owner, name="Группа А", description="Английский язык")
    new_id = lesson_factory(
        group_id=group_id,
        status="planned",
        price=None,
        starts_at=datetime(2026, 5, 17, 15, 0, tzinfo=UTC),
    )
    old_id = lesson_factory(
        group_id=group_id,
        status="completed",
        price=None,
        starts_at=datetime(2026, 4, 26, 15, 0, tzinfo=UTC),
    )

    response = client.get(f"/tutor/groups/{group_id}/lessons")
    html = response.text

    assert response.status_code == 200
    assert html.index("17.05.2026") < html.index("26.04.2026")
    # Строка кликабельна и открывает модалку урока во втором слое.
    assert f'hx-get="/tutor/lessons/{new_id}/edit"' in html
    assert f'hx-get="/tutor/lessons/{old_id}/edit"' in html
    assert 'hx-target="#modal-lesson"' in html
    # Подписи статуса и предмет (описание группы), как в референсе вкладки.
    assert "Запланирован" in html
    assert "Проведён" in html
    assert "Английский язык" in html


def test_panel_rows_show_homework_indicator(
    owner, client, group_factory, lesson_factory
):
    """«ДЗ: есть» у урока с заданием, «ДЗ: нет» без записи и у «Не задано»."""
    group_id = group_factory(tutor_id=owner)
    assigned_id = lesson_factory(group_id=group_id, price=None)
    none_id = lesson_factory(group_id=group_id, price=None)
    unassigned_id = lesson_factory(group_id=group_id, price=None)
    _homework(assigned_id, status="assigned")
    _homework(unassigned_id, status="not_assigned")

    html = client.get(f"/tutor/groups/{group_id}/lessons").text

    assert html.count("ДЗ: есть") == 1
    assert html.count("ДЗ: нет") == 2


def test_panel_status_filter(owner, client, group_factory, lesson_factory):
    """Чипы «Проведённые»/«Запланированные» фильтруют по статусу урока."""
    group_id = group_factory(tutor_id=owner)
    lesson_factory(
        group_id=group_id,
        status="planned",
        price=None,
        starts_at=datetime(2026, 5, 17, 15, 0, tzinfo=UTC),
    )
    lesson_factory(
        group_id=group_id,
        status="completed",
        price=None,
        starts_at=datetime(2026, 4, 26, 15, 0, tzinfo=UTC),
    )

    planned = client.get(f"/tutor/groups/{group_id}/lessons?status=planned").text
    completed = client.get(
        f"/tutor/groups/{group_id}/lessons?status=completed"
    ).text
    # Неизвестное значение — «Все».
    everything = client.get(f"/tutor/groups/{group_id}/lessons?status=мусор").text

    assert "17.05.2026" in planned
    assert "26.04.2026" not in planned
    assert "26.04.2026" in completed
    assert "17.05.2026" not in completed
    assert "17.05.2026" in everything and "26.04.2026" in everything


def test_panel_empty_states(owner, client, group_factory):
    """Без занятий — приглашение; с фильтром без совпадений — пояснение."""
    group_id = group_factory(tutor_id=owner)

    empty = client.get(f"/tutor/groups/{group_id}/lessons").text
    filtered = client.get(f"/tutor/groups/{group_id}/lessons?status=planned").text

    assert "У группы пока нет занятий." in empty
    assert "Нет занятий с таким статусом." in filtered


def test_panel_of_foreign_group_is_404(owner, client, group_factory, tutor_factory):
    """Чужая группа и несуществующая неразличимы: 404, а не 403."""
    foreign_tutor = tutor_factory(email="group-lessons-foreign@example.com")
    foreign_group = group_factory(tutor_id=foreign_tutor)

    assert client.get(f"/tutor/groups/{foreign_group}/lessons").status_code == 404
    assert client.get("/tutor/groups/missing-id/lessons").status_code == 404


def test_panel_requires_login(client, group_factory):
    """Без сессии панель не отдаётся."""
    group_id = group_factory(name="Чья-то группа")
    response = client.get(f"/tutor/groups/{group_id}/lessons", follow_redirects=False)
    assert response.status_code == 303


# --------------------------------------------------------------------------
# Второй слой модалок: модалка урока поверх модалки группы
# --------------------------------------------------------------------------


def test_groups_page_has_stacked_modal_container(owner, client):
    """Страница групп несёт контейнер второго слоя и скрипты модалки урока."""
    html = client.get("/tutor/groups").text

    assert 'id="modal-lesson"' in html
    assert "/static/lessons.js" in html


def test_lesson_edit_targets_stacked_layer_from_header(
    owner, client, group_factory, lesson_factory
):
    """GET с `HX-Target: modal-lesson` открывает форму во втором слое."""
    group_id = group_factory(tutor_id=owner)
    lesson_id = _lesson(lesson_factory, group_id)

    stacked = client.get(
        f"/tutor/lessons/{lesson_id}/edit", headers={"HX-Target": "modal-lesson"}
    )
    plain = client.get(f"/tutor/lessons/{lesson_id}/edit", headers=HTMX)

    assert 'hx-target="#modal-lesson"' in stacked.text
    # Страница уроков и календарь по-прежнему открывают форму в `#modal`.
    assert 'hx-target="#modal"' in plain.text
    assert 'hx-target="#modal-lesson"' not in plain.text


def test_lesson_update_error_stays_in_stacked_layer(
    owner, client, group_factory, lesson_factory
):
    """Ошибка валидации возвращается во второй слой, а не в `#modal`."""
    group_id = group_factory(tutor_id=owner)
    lesson_id = _lesson(lesson_factory, group_id)

    response = client.post(
        f"/tutor/lessons/{lesson_id}",
        data={"starts_at": "2026-05-17T15:00", "duration_min": "60", "rating": "9"},
        headers={**HTMX, "HX-Target": "modal-lesson"},
    )

    assert response.status_code == 200
    assert "HX-Trigger" not in response.headers
    assert 'hx-target="#modal-lesson"' in response.text


def test_lesson_delete_from_stacked_layer_closes_and_notifies(
    owner, client, group_factory, lesson_factory
):
    """Удаление во втором слое: пустой ответ и `lesson-saved` для списка."""
    group_id = group_factory(tutor_id=owner)
    lesson_id = _lesson(lesson_factory, group_id)

    response = client.post(
        f"/tutor/lessons/{lesson_id}/delete", headers=HTMX
    )

    assert response.status_code == 200
    assert response.text == ""
    assert response.headers["HX-Trigger"] == "lesson-saved"
