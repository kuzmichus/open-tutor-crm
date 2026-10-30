"""Тесты страницы «Задачи» (`/tutor/tasks`, спека task-management).

Поведение проверяется через HTTP — теми же маршрутами, что у пользователя
(правило AGENTS.md): карточка ищется по тексту названия, действия — по
адресам форм, изоляция — отсутствием чужих задач в разметке и 404 на
действия с чужой задачей.

Даты срока строятся от «сегодня» в зоне репетитора (в тестах — UTC):
прибитые к октябрю тесты сломались бы через год.
"""

from datetime import UTC, datetime, timedelta
import html
import json
import re

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.task.models.task import Task
from app.task.models.task_student import TaskStudent
from app.tutor.services.clock import utcnow

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


def _attr_json(markup: str, name: str) -> object:
    """JSON из `data-`атрибута (Jinja экранирует кириллицу)."""
    match = re.search(rf"""{name}=(?:'([^']*)'|"([^"]*)")""", markup)
    assert match, f"нет атрибута {name} в ответе"
    raw = match.group(1) if match.group(1) is not None else match.group(2)
    return json.loads(html.unescape(raw))


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="tasks-page@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "tasks-page@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


@pytest.fixture()
def task_factory():
    """Создаёт задачу и возвращает её id (ученики — через `students`)."""

    def _create(
        tutor_id: str,
        title: str = "Позвонить Маме Ване",
        stage: str = "new",
        priority: str = "medium",
        due_date=None,
        students: list[str] | None = None,
        **extra,
    ):
        with SessionLocal() as session:
            task = Task(
                tutor_id=tutor_id,
                title=title,
                stage=stage,
                priority=priority,
                due_date=due_date,
                **extra,
            )
            session.add(task)
            session.flush()
            for student_id in students or []:
                session.add(TaskStudent(task_id=task.id, student_id=student_id))
            session.commit()
            return task.id

    return _create


def _today():
    """Сегодняшняя дата в зоне тестового репетитора (UTC)."""
    return utcnow().date()


def _stored(task_id: str) -> Task:
    """Свежая строка задачи из БД."""
    with SessionLocal() as session:
        return session.get(Task, task_id)


# --------------------------------------------------------------------------
# Доступ
# --------------------------------------------------------------------------


def test_page_requires_login(client):
    """Без сессии страница редиректит на вход, а не отдаёт разметку."""
    response = client.get("/tutor/tasks", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/tutor/login")


def test_empty_board_shows_all_columns(client, owner):
    """Пустая доска: четыре колонки этапов, пустые состояния, активный пункт."""
    response = client.get("/tutor/tasks")
    assert response.status_code == 200
    page = response.text
    assert "Задачи" in page
    assert "Планирование дел" in page
    for label in ("Новые", "В работе", "На проверке", "Готово"):
        assert label in page
    assert page.count("Пусто") == 4
    # Пункт сайдбара «Задачи» подсвечен.
    assert "nav-item--active" in page
    # Кнопка создания ведёт в диалог.
    assert 'hx-get="/tutor/tasks/new"' in page


def test_dialog_has_no_responsible_field(client, owner):
    """В форме нет поля «Ответственный» — задачи ставит себе сам педагог."""
    response = client.get("/tutor/tasks/new")
    assert response.status_code == 200
    page = response.text
    assert "Новая задача" in page
    assert "Ответственн" not in page
    for label in ("Название", "Приоритет", "Срок", "Этап", "Описание", "Ученики"):
        assert label in page


# --------------------------------------------------------------------------
# Создание и правка
# --------------------------------------------------------------------------


def test_create_task_appears_on_board(client, owner, student_factory):
    """Созданная задача появляется в колонке своего этапа с подписями."""
    student_id = student_factory(tutor_id=owner, first_name="Маме")
    due = (_today() + timedelta(days=3)).isoformat()

    response = client.post(
        "/tutor/tasks",
        data={
            "title": "Подготовить отчёт",
            "priority": "high",
            "stage": "in_progress",
            "due_date": due,
            "description": "Детали",
            "students": student_id,
        },
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "task-saved"
    assert response.text == ""

    page = client.get("/tutor/tasks").text
    assert "Подготовить отчёт" in page
    assert "Высокий" in page
    assert "Маме" in page
    # Задача стоит в колонке «В работе», а не в «Новые».
    column = page.split('id="task-column-in_progress"')[1].split("</section>")[0]
    assert "Подготовить отчёт" in column


def test_create_task_without_title_returns_dialog_with_error(client, owner):
    """Пустое название — диалог с ошибкой, а не созданная задача."""
    response = client.post(
        "/tutor/tasks",
        data={"title": "  ", "priority": "medium", "stage": "new"},
        headers=HTMX,
    )
    assert response.status_code == 200
    assert "Укажите название задачи." in response.text
    assert 'id="task-dialog"' in response.text

    with SessionLocal() as session:
        assert session.scalars(select(Task)).all() == []


def test_create_task_with_foreign_student_is_rejected(
    client, owner, student_factory, tutor_factory
):
    """Чужой ученик в форме — ошибка, привязка не создаётся."""
    other_id = tutor_factory(email="other-tasks@example.com")
    foreign_student = student_factory(tutor_id=other_id)

    response = client.post(
        "/tutor/tasks",
        data={"title": "Задача", "students": foreign_student},
        headers=HTMX,
    )
    assert response.status_code == 200
    assert "Выбранный ученик не найден." in response.text

    with SessionLocal() as session:
        assert session.scalars(select(Task)).all() == []


def test_create_without_js_redirects(client, owner):
    """POST без HX-Request отвечает 303 на страницу задач."""
    response = client.post(
        "/tutor/tasks",
        data={"title": "Без JS"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/tasks"


def test_edit_dialog_is_prefilled(client, owner, task_factory, student_factory):
    """Диалог правки показывает сохранённые значения и учеников."""
    student_id = student_factory(tutor_id=owner, first_name="Иван")
    task_id = task_factory(
        owner,
        title="Позвонить Маме Ване",
        stage="review",
        priority="low",
        due_date=_today(),
        students=[student_id],
        description="Комментарий",
    )

    response = client.get(f"/tutor/tasks/{task_id}/edit")
    assert response.status_code == 200
    page = response.text
    assert "Позвонить Маме Ване" in page
    # Срок подставлен в поле даты тем же значением, что сохранён.
    assert f'value="{_today().strftime("%Y-%m-%d")}"' in page
    assert "Комментарий" in page
    # Ученик приходит в стартовом состоянии виджета: Jinja экранирует
    # кириллицу в JSON, поэтому значение разбирается, а не ищется строкой.
    selected = _attr_json(page, "data-selected")
    assert [row["id"] for row in selected] == [student_id]
    assert selected[0]["name"] == "Иван"
    # Текущий этап выбран в селекте.
    assert 'value="review"' in page
    assert 'value="low"' in page


def test_update_task_changes_fields_and_students(
    client, owner, task_factory, student_factory
):
    """Сохранение меняет поля и состав учеников."""
    first = student_factory(tutor_id=owner, first_name="Первый")
    second = student_factory(tutor_id=owner, first_name="Второй")
    task_id = task_factory(owner, students=[first])

    response = client.post(
        f"/tutor/tasks/{task_id}",
        data={
            "title": "Обновлённая",
            "priority": "high",
            "stage": "review",
            "students": second,
        },
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "task-saved"

    task = _stored(task_id)
    assert task.title == "Обновлённая"
    assert task.priority == "high"
    assert task.stage == "review"
    with SessionLocal() as session:
        linked = session.scalars(
            select(TaskStudent.student_id).where(TaskStudent.task_id == task_id)
        ).all()
    assert linked == [second]


# --------------------------------------------------------------------------
# Этапы и завершение
# --------------------------------------------------------------------------


def test_stage_move_sets_and_clears_completion(client, owner, task_factory):
    """Переход в «Готово» ставит момент завершения, возврат — сбрасывает."""
    task_id = task_factory(owner, stage="new")

    response = client.post(
        f"/tutor/tasks/{task_id}/stage", data={"stage": "done"}, headers=HTMX
    )
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "task-saved"
    task = _stored(task_id)
    assert task.stage == "done"
    assert task.completed_at is not None

    client.post(
        f"/tutor/tasks/{task_id}/stage", data={"stage": "in_progress"}, headers=HTMX
    )
    task = _stored(task_id)
    assert task.stage == "in_progress"
    assert task.completed_at is None


def test_repeated_done_keeps_first_completion_moment(
    client, owner, task_factory
):
    """Повторный перевод в «Готово» не сдвигает дату завершения."""
    task_id = task_factory(owner, stage="done")
    with SessionLocal() as session:
        task = session.get(Task, task_id)
        task.completed_at = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        session.commit()

    client.post(
        f"/tutor/tasks/{task_id}/stage", data={"stage": "done"}, headers=HTMX
    )
    assert _stored(task_id).completed_at.replace(tzinfo=UTC) == datetime(
        2026, 1, 5, 10, 0, tzinfo=UTC
    )


def test_unknown_stage_is_rejected(client, owner, task_factory):
    """Мусор в этапе — 400, задача не меняется."""
    task_id = task_factory(owner, stage="new")
    response = client.post(
        f"/tutor/tasks/{task_id}/stage", data={"stage": "bogus"}, headers=HTMX
    )
    assert response.status_code == 400
    assert _stored(task_id).stage == "new"


def test_stage_move_without_htmx_redirects(client, owner, task_factory):
    """POST смены этапа без HX-Request отвечает 303 — работает и без JS."""
    task_id = task_factory(owner, stage="new")
    response = client.post(
        f"/tutor/tasks/{task_id}/stage",
        data={"stage": "done"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/tasks"
    assert _stored(task_id).stage == "done"


# --------------------------------------------------------------------------
# Удаление
# --------------------------------------------------------------------------


def test_delete_task_removes_it_and_links(client, owner, task_factory, student_factory):
    """Удаление убирает задачу и её связки с учениками."""
    student_id = student_factory(tutor_id=owner)
    task_id = task_factory(owner, students=[student_id])

    response = client.post(f"/tutor/tasks/{task_id}/delete", headers=HTMX)
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "task-saved"

    with SessionLocal() as session:
        assert session.get(Task, task_id) is None
        assert session.scalars(select(TaskStudent)).all() == []


# --------------------------------------------------------------------------
# Виды страницы
# --------------------------------------------------------------------------


def test_list_view_groups_by_due_date(client, owner, task_factory):
    """Список: «Сегодня» (включая просроченные), «Предстоящие», «Завершено»."""
    today = _today()
    task_factory(owner, title="Сегодняшняя", due_date=today)
    task_factory(owner, title="Просроченная", due_date=today - timedelta(days=2))
    task_factory(owner, title="Будущая", due_date=today + timedelta(days=5))
    task_factory(owner, title="Завершённая", stage="done", due_date=today)

    page = client.get("/tutor/tasks?view=list").text
    assert "Сегодня" in page
    assert "Предстоящие" in page
    assert "Завершено" in page

    today_block = page.split('id="task-group-today"')[1].split("</section>")[0]
    assert "Сегодняшняя" in today_block
    assert "Просроченная" in today_block
    assert "Будущая" not in today_block
    assert "Завершённая" not in today_block

    upcoming = page.split('id="task-group-upcoming"')[1].split("</section>")[0]
    assert "Будущая" in upcoming
    assert "Сегодняшняя" not in upcoming

    done = page.split('id="task-group-done"')[1].split("</section>")[0]
    assert "Завершённая" in done


def test_overdue_task_is_marked(client, owner, task_factory):
    """Просроченная задача помечена и в доске, и в списке."""
    task_factory(owner, title="Старая", due_date=_today() - timedelta(days=1))
    for url in ("/tutor/tasks", "/tutor/tasks?view=list"):
        page = client.get(url).text
        assert "task-card--overdue" in page
        assert "task-card__due--overdue" in page


def test_student_filter_narrows_both_views(
    client, owner, task_factory, student_factory
):
    """Фильтр по ученику показывает только его задачи в обоих видах."""
    mine = student_factory(tutor_id=owner, first_name="Своя")
    task_factory(owner, title="Задача Своей", students=[mine])
    task_factory(owner, title="Задача без ученика")

    for url in (
        f"/tutor/tasks?student={mine}",
        f"/tutor/tasks?view=list&student={mine}",
    ):
        page = client.get(url).text
        assert "Задача Своей" in page
        assert "Задача без ученика" not in page


def test_list_partial_returns_fragment_only(client, owner, task_factory):
    """Партиал /list отдаёт контент без сайдбара — для контейнера страницы."""
    task_factory(owner, title="Задача в партиале")

    response = client.get("/tutor/tasks/list")
    assert response.status_code == 200
    assert "Задача в партиале" in response.text
    assert 'class="sidebar"' not in response.text
    assert "Планирование дел" not in response.text


def test_board_ships_drag_and_drop_markup(client, owner, task_factory):
    """Доска отдаёт атрибуты, на которых работает перетаскивание карточек."""
    task_id = task_factory(owner, title="Перетащи меня")

    page = client.get("/tutor/tasks").text
    # Карточку можно схватить, а JS знает её id и колонку-источник.
    assert f'data-task-id="{task_id}"' in page
    assert 'draggable="true"' in page
    # Тело колонки — цель переноса: этап лежит в data-атрибуте.
    for stage in ("new", "in_progress", "review", "done"):
        assert f'data-stage="{stage}"' in page


# --------------------------------------------------------------------------
# Изоляция по репетитору
# --------------------------------------------------------------------------


def test_page_isolates_by_tutor(client, owner, task_factory, tutor_factory):
    """Чужие задачи не видны ни на доске, ни в списке."""
    other_id = tutor_factory(email="other-board@example.com")
    task_factory(other_id, title="Чужая задача")

    for url in ("/tutor/tasks", "/tutor/tasks?view=list", "/tutor/tasks/list"):
        page = client.get(url).text
        assert "Чужая задача" not in page


def test_foreign_task_actions_are_404(
    client, owner, task_factory, tutor_factory
):
    """Правка, сохранение, удаление и смена этапа чужой задачи — 404."""
    other_id = tutor_factory(email="other-actions@example.com")
    task_id = task_factory(other_id, title="Чужая")

    assert client.get(f"/tutor/tasks/{task_id}/edit").status_code == 404
    assert (
        client.post(
            f"/tutor/tasks/{task_id}",
            data={"title": "Взлом"},
            headers=HTMX,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/tutor/tasks/{task_id}/stage", data={"stage": "done"}, headers=HTMX
        ).status_code
        == 404
    )
    assert (
        client.post(f"/tutor/tasks/{task_id}/delete", headers=HTMX).status_code
        == 404
    )
    # Задача не изменилась.
    assert _stored(task_id).title == "Чужая"


def test_missing_task_is_404(client, owner):
    """Несуществующая задача отвечает так же, как чужая, — 404."""
    assert client.get("/tutor/tasks/нет-такой/edit").status_code == 404


# --------------------------------------------------------------------------
# Счётчик просроченных задач в сайдбаре
# --------------------------------------------------------------------------


def test_sidebar_badge_container_for_tasks(client, owner):
    """Сайдбар несёт контейнер счётчика «Задачи» с htmx-подгрузкой.

    Контейнер пустой: число подгружает партиал `/tutor/tasks/count` при
    загрузке страницы, перечитывает каждые 30 секунд (просрочка наступает
    сама, без событий у педагога) и по `task-saved` — действия с задачей
    обновляют счётчик мгновенно.
    """
    page = client.get("/tutor/tasks").text
    start = page.index('<aside class="sidebar"')
    sidebar = page[start : page.index("</aside>", start)]

    assert 'id="nav-badge-tasks"' in sidebar
    assert 'hx-get="/tutor/tasks/count"' in sidebar
    assert "every 30s" in sidebar
    assert "task-saved from:body" in sidebar
    # Счётчик — часть сайдбара, а не страницы задач: виден отовсюду.
    home = client.get("/tutor/").text
    assert 'id="nav-badge-tasks"' in home


def test_count_partial_shows_overdue_only(client, owner, task_factory):
    """Партиал отдаёт число просроченных: срок раньше сегодня и не «Готово».

    Срок сегодня — работа на сегодня, но ещё не просрочка (то же правило,
    что у метки карточки); завершённые и задачи без срока не считаются.
    """
    today = _today()
    task_factory(owner, title="Вчерашняя", due_date=today - timedelta(days=1))
    task_factory(
        owner,
        title="Старая в работе",
        due_date=today - timedelta(days=5),
        stage="in_progress",
    )
    task_factory(owner, title="Срок сегодня", due_date=today)
    task_factory(owner, title="Будущая", due_date=today + timedelta(days=2))
    task_factory(
        owner,
        title="Просрочена, но готова",
        due_date=today - timedelta(days=3),
        stage="done",
    )
    task_factory(owner, title="Без срока")

    response = client.get("/tutor/tasks/count")
    assert response.status_code == 200
    assert response.text == "2"


def test_count_partial_is_empty_without_overdue(client, owner, task_factory):
    """Без просроченных — пустое тело: контейнер остаётся без кружка."""
    task_factory(owner, title="Срок сегодня", due_date=_today())

    response = client.get("/tutor/tasks/count")
    assert response.status_code == 200
    assert response.text == ""


def test_count_partial_isolates_by_tutor(
    client, owner, tutor_factory, task_factory
):
    """Чужие просроченные задачи в счётчик не попадают."""
    task_factory(owner, title="Моя просрочка", due_date=_today() - timedelta(days=1))
    other_id = tutor_factory(email="tasks-count-other@example.com")
    task_factory(
        other_id, title="Чужая просрочка", due_date=_today() - timedelta(days=1)
    )

    assert client.get("/tutor/tasks/count").text == "1"


def test_count_partial_requires_login(client):
    """Без сессии партиал редиректит на вход, а не отдаёт число."""
    response = client.get("/tutor/tasks/count", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/tutor/login")


def test_count_partial_updates_after_stage_move(client, owner, task_factory):
    """Смена этапа меняет счётчик: завершение убирает, возврат возвращает.

    Партиал перечитывается по `task-saved`, который шлёт и смена этапа,
    и сохранение формы, и удаление.
    """
    task_id = task_factory(
        owner, title="Просрочка", due_date=_today() - timedelta(days=1)
    )
    assert client.get("/tutor/tasks/count").text == "1"

    client.post(
        f"/tutor/tasks/{task_id}/stage", data={"stage": "done"}, headers=HTMX
    )
    assert client.get("/tutor/tasks/count").text == ""

    client.post(
        f"/tutor/tasks/{task_id}/stage",
        data={"stage": "in_progress"},
        headers=HTMX,
    )
    assert client.get("/tutor/tasks/count").text == "1"
