"""Тесты единых страниц кабинета родителя (change parent-cabinet-unified-pages).

Поведение через HTTP тем же путём, что у пользователя: общие страницы
«Уроки» / «Домашние задания» / «Финансы», редиректы вместо страниц
ребёнка, плоский сайдбар, вкладки по детям и изоляция по контакту.
Даты уроков — `utcnow() ± timedelta` (фиксированные даты протухают).
"""

from datetime import timedelta

import pytest

from app.calendar.services.week import week_start
from app.database import SessionLocal
from app.homework.models.homework import Homework
from app.student.models.contact import Contact
from app.student.models.student_contact import StudentContact
from app.tutor.services.clock import utcnow
from app.tutor.services.password_hasher import PasswordHasher

PASSWORD = "Пароль-1"
HTMX = {"HX-Request": "true"}

MONDAY = week_start(utcnow().date())


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="unified-owner@example.com", password=PASSWORD, timezone="UTC")
    client.post(
        "/tutor/login",
        data={"email": "unified-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _make_contact(tutor_id: str, full_name: str = "Мария Смирнова") -> str:
    with SessionLocal() as db:
        contact = Contact(tutor_id=tutor_id, full_name=full_name)
        db.add(contact)
        db.commit()
        return contact.id


def _link(student_id: str, contact_id: str) -> None:
    with SessionLocal() as db:
        db.add(StudentContact(student_id=student_id, contact_id=contact_id))
        db.commit()


def _seed_parent_access(contact_id: str, email: str = "mama@example.com") -> None:
    from app.cabinet.models.contact_access import ContactAccess

    with SessionLocal() as db:
        db.add(
            ContactAccess(
                contact_id=contact_id,
                email=email,
                password_hash=PasswordHasher().hash(PASSWORD),
            )
        )
        db.commit()


def _login_parent(client) -> None:
    client.post(
        "/parent/login",
        data={"email": "mama@example.com", "password": PASSWORD},
    )


def _logged_in_parent(client, tutor_id: str) -> str:
    """Контакт с доступом и открытой сессией родителя; возвращает contact_id."""
    contact_id = _make_contact(tutor_id)
    _seed_parent_access(contact_id)
    _login_parent(client)
    return contact_id


def _at(day_offset: int, hour: int):
    """Момент недели MONDAY (репетитор теста в зоне UTC)."""
    from datetime import UTC, datetime, time

    return datetime.combine(
        MONDAY + timedelta(days=day_offset), time(hour, 0), tzinfo=UTC
    )


def _today_at(hour: int):
    """Полдень «сегодня» зоны UTC: сводка дня видит его в любой момент суток."""
    from datetime import UTC, datetime, time

    return datetime.combine(utcnow().date(), time(hour, 0), tzinfo=UTC)


# --------------------------------------------------------------------------
# Страница «Уроки»: сетка недели всех детей
# --------------------------------------------------------------------------


def test_parent_lessons_shows_both_children(
    client, owner, student_factory, lesson_factory
):
    """Сетка показывает уроки обоих детей, карточки подписаны именами."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    borya = student_factory(tutor_id=owner, first_name="Боря")
    _link(anya, contact_id)
    _link(borya, contact_id)
    lesson_factory(student_id=anya, status="planned", starts_at=_at(1, 10))
    lesson_factory(student_id=borya, status="planned", starts_at=_at(2, 12))

    page = client.get("/parent/lessons").text
    assert "Аня" in page
    assert "Боря" in page
    assert 'id="parent-calendar"' in page
    assert "cal-event" in page


def test_parent_lessons_rating_star_on_graded_lesson(
    client, owner, student_factory, lesson_factory
):
    """У оценённого прошедшего урока в сетке видна звёздочка «★ N»."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    _link(anya, contact_id)
    graded = lesson_factory(
        student_id=anya, status="completed", starts_at=_at(1, 10)
    )
    with SessionLocal() as db:
        from app.lesson.models.lesson import Lesson

        db.get(Lesson, graded).rating = 5
        db.commit()

    page = client.get("/parent/lessons").text
    assert "★ 5" in page


def test_parent_lessons_nearest_notice_across_children(
    client, owner, student_factory, lesson_factory
):
    """Плашка «Ближайшее занятие» — ближайшее среди всех детей, с именем."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    borya = student_factory(tutor_id=owner, first_name="Боря")
    _link(anya, contact_id)
    _link(borya, contact_id)
    # Прошедший урок не кандидат; ближайший — у Бори, не у Ани.
    lesson_factory(
        student_id=anya, status="planned", starts_at=utcnow() + timedelta(days=3)
    )
    lesson_factory(
        student_id=borya, status="planned", starts_at=utcnow() + timedelta(days=1)
    )

    page = client.get("/parent/lessons").text
    assert "Ближайшее занятие" in page
    assert "Боря" in page


def test_parent_lessons_week_from_start_param(
    client, owner, student_factory, lesson_factory
):
    """`?start=` выбирает неделю: урок предыдущей недели показан в ней."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    _link(anya, contact_id)
    prev_monday = MONDAY - timedelta(days=7)
    from datetime import UTC, datetime, time

    lesson_factory(
        student_id=anya,
        status="planned",
        starts_at=datetime.combine(prev_monday, time(10, 0), tzinfo=UTC),
    )

    page = client.get(f"/parent/lessons?start={prev_monday.isoformat()}").text
    # Карточка урока стоит в колонке своего дня (ISO-дата в data-date).
    assert f'data-date="{prev_monday.isoformat()}"' in page
    assert "Аня" in page


def test_parent_lessons_requires_contact_session(client):
    """Без сессии контакта — редирект на вход родителя."""
    response = client.get("/parent/lessons", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/parent/login"


def test_parent_lessons_htmx_returns_partial_only(
    client, owner, student_factory, lesson_factory
):
    """Листание недель отдаёт только область календаря, без каркаса страницы."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    _link(anya, contact_id)
    lesson_factory(student_id=anya, status="planned", starts_at=_at(1, 10))

    page = client.get("/parent/lessons", headers=HTMX).text
    assert "<!DOCTYPE html>" not in page
    assert "cal-grid" in page
    # Листание ведёт на общую страницу, а не на адрес ученического кабинета.
    assert 'hx-get="/parent/lessons?start=' in page


def test_parent_lessons_badge_shows_first_child_timezone(
    client, owner, student_factory
):
    """Бейдж пояса — зона первого ребёнка; без пояса — зона педагога."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(
        tutor_id=owner, first_name="Аня", timezone="Europe/Moscow"
    )
    borya = student_factory(
        tutor_id=owner, first_name="Боря", timezone="Asia/Yekaterinburg"
    )
    _link(anya, contact_id)
    _link(borya, contact_id)

    page = client.get("/parent/lessons").text
    assert "Europe/Moscow" in page
    assert "Asia/Yekaterinburg" not in page


# --------------------------------------------------------------------------
# Плоская навигация и редиректы
# --------------------------------------------------------------------------


def test_parent_sidebar_is_flat(client, owner, student_factory):
    """Меню содержит ровно четыре пункта; имён детей в сайдбаре нет."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    borya = student_factory(tutor_id=owner, first_name="Боря")
    _link(anya, contact_id)
    _link(borya, contact_id)

    page = client.get("/parent/lessons").text
    sidebar = page[page.index('class="sidebar"') : page.index("</aside>")]
    for href in (
        'href="/parent/lessons"',
        'href="/parent/homework"',
        'href="/parent/finance"',
        'href="/parent/profile"',
    ):
        assert href in sidebar
    # Секции по детям убраны: имена в меню не встречаются (в сетке — да).
    assert "Аня" not in sidebar
    assert "Боря" not in sidebar


def test_parent_root_redirects_to_lessons(client, owner):
    """/parent отдаёт 303 на /parent/lessons."""
    _logged_in_parent(client, owner)
    response = client.get("/parent", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/parent/lessons"


def test_parent_student_lessons_redirects(client, owner, student_factory):
    """Старый адрес страницы ребёнка ведёт на общую страницу «Уроки»."""
    _logged_in_parent(client, owner)
    own = student_factory(tutor_id=owner)
    stranger = student_factory(tutor_id=owner)

    for student_id in (own, stranger, "нет-такого-ученика"):
        response = client.get(f"/parent/students/{student_id}", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/parent/lessons"


def test_parent_student_homework_redirects_with_child_param(
    client, owner, student_factory
):
    """Старый адрес ДЗ ребёнка ведёт на общую страницу с открытой вкладкой."""
    _logged_in_parent(client, owner)
    own = student_factory(tutor_id=owner)

    response = client.get(
        f"/parent/students/{own}/homework", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/parent/homework?child={own}"


def test_parent_root_redirects_without_session(client):
    """Без сессии `/parent` всё равно редирект на «Уроки», не на ошибку."""
    response = client.get("/parent", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/parent/lessons"


# --------------------------------------------------------------------------
# Страница «Домашние задания»: вкладки по детям
# --------------------------------------------------------------------------


def test_parent_homework_default_tab_is_first_child(
    client, owner, student_factory, lesson_factory
):
    """Без параметра активна вкладка первого ребёнка с его заданиями."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    borya = student_factory(tutor_id=owner, first_name="Боря")
    _link(anya, contact_id)
    _link(borya, contact_id)
    lesson_id = lesson_factory(student_id=anya, status="planned", price=0)
    with SessionLocal() as db:
        db.add(
            Homework(
                lesson_id=lesson_id, assignment="Страница 12", status="assigned"
            )
        )
        db.commit()

    page = client.get("/parent/homework").text
    # Вкладки на обоих детей; активная — первый по порядку.
    assert f'href="/parent/homework?child={anya}"' in page
    assert f'href="/parent/homework?child={borya}"' in page
    assert "parent-tabs__tab--active" in page
    # Задания первого ребёнка на активной вкладке.
    assert "Страница 12" in page


def test_parent_homework_foreign_child_404(client, owner, student_factory):
    """Вкладка чужого ребёнка неразличима с несуществующей страницей — 404."""
    contact_id = _logged_in_parent(client, owner)
    own = student_factory(tutor_id=owner)
    _link(own, contact_id)
    stranger = student_factory(tutor_id=owner)

    assert client.get(f"/parent/homework?child={stranger}").status_code == 404
    assert client.get("/parent/homework?child=нет-такого").status_code == 404


def test_parent_homework_tabs_switch_and_hide_teacher_note(
    client, owner, student_factory, lesson_factory
):
    """Вкладка второго ребёнка — его задания; заметки педагога нигде нет."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    borya = student_factory(tutor_id=owner, first_name="Боря")
    _link(anya, contact_id)
    _link(borya, contact_id)
    anya_lesson = lesson_factory(student_id=anya, status="planned", price=0)
    borya_lesson = lesson_factory(student_id=borya, status="planned", price=0)
    with SessionLocal() as db:
        db.add(
            Homework(
                lesson_id=anya_lesson,
                assignment="Задание Ани",
                status="assigned",
                teacher_note="Секретная заметка педагога",
            )
        )
        db.add(
            Homework(
                lesson_id=borya_lesson,
                assignment="Задание Бори",
                status="assigned",
            )
        )
        db.commit()

    page = client.get(f"/parent/homework?child={borya}").text
    assert "Задание Бори" in page
    assert "Задание Ани" not in page
    # Заметка педагога скрыта от ученика — родителю не показывается.
    assert "Секретная заметка" not in page


def test_parent_homework_deadline_notice_rendered(
    client, owner, student_factory, lesson_factory
):
    """При горящем сроке над вкладками видна плашка."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    _link(anya, contact_id)
    lesson_id = lesson_factory(student_id=anya, status="planned", price=0)
    with SessionLocal() as db:
        from datetime import UTC, datetime, time

        due_today = datetime.combine(utcnow().date(), time(12, 0), tzinfo=UTC)
        db.add(
            Homework(
                lesson_id=lesson_id,
                assignment="Страница 12",
                status="assigned",
                due_at=due_today,
            )
        )
        db.commit()

    page = client.get("/parent/homework").text
    assert "истекает срок сдачи" in page
    assert "notice-banner" in page


def test_parent_homework_without_children_empty_state(client, owner):
    """Контакт без детей: вкладок нет, пустое состояние."""
    _logged_in_parent(client, owner)
    page = client.get("/parent/homework").text
    assert "Ученики пока не привязаны" in page


# --------------------------------------------------------------------------
# Страница «Финансы»: вкладки по детям
# --------------------------------------------------------------------------


def test_parent_finance_total_on_any_tab_history_only_active(
    client, owner, student_factory, operation_factory
):
    """Итог виден на любой вкладке; история — только активного ребёнка."""
    contact_id = _logged_in_parent(client, owner)
    anya = student_factory(tutor_id=owner, first_name="Аня")
    borya = student_factory(tutor_id=owner, first_name="Боря")
    _link(anya, contact_id)
    _link(borya, contact_id)
    operation_factory(student_id=anya, kind="payment", amount=3000, status="paid")
    operation_factory(student_id=borya, kind="payment", amount=1500, status="paid")
    operation_factory(student_id=borya, kind="lesson", amount=600)

    page = client.get("/parent/finance").text
    # Общий итог: 3000 + (1500 − 600) = 3 900 ₽ (money() — неразрывные пробелы).
    assert "Общий баланс по детям" in page
    assert "3\u00a0900\u00a0₽" in page
    # Дефолтная вкладка — первый ребёнок; только его блок.
    assert "Аня" in page
    assert "3\u00a0000\u00a0₽" in page
    assert "1\u00a0500\u00a0₽" not in page

    # Вкладка второго ребёнка: итог тот же, история — этого ребёнка.
    page = client.get(f"/parent/finance?child={borya}").text
    assert "3\u00a0900\u00a0₽" in page
    assert "1\u00a0500\u00a0₽" in page
    assert "600\u00a0₽" in page
    assert "3\u00a0000\u00a0₽" not in page


def test_parent_finance_foreign_child_404(client, owner, student_factory):
    """Вкладка чужого ребёнка в финансах — 404."""
    contact_id = _logged_in_parent(client, owner)
    own = student_factory(tutor_id=owner)
    _link(own, contact_id)
    stranger = student_factory(tutor_id=owner)

    assert client.get(f"/parent/finance?child={stranger}").status_code == 404


def test_parent_finance_without_children_total_zero(client, owner):
    """Контакт без детей: «Финансы» показывают только общий итог (0)."""
    _logged_in_parent(client, owner)
    page = client.get("/parent/finance").text
    assert "Общий баланс по детям" in page
    assert "0\u00a0₽" in page


# --------------------------------------------------------------------------
# Алерты на всех страницах кабинета родителя
# --------------------------------------------------------------------------


def test_parent_notice_balance_partial(
    client, owner, student_factory, lesson_factory
):
    """Партиал нехватки: пустое тело без данных, текст при нехватке."""
    contact_id = _logged_in_parent(client, owner)
    # Денег хватает (занятий с ценой нет) — пустой ответ.
    assert client.get("/parent/notices/balance").text.strip() == ""

    anya = student_factory(tutor_id=owner, first_name="Аня")
    _link(anya, contact_id)
    lesson_factory(
        student_id=anya, status="planned", price=1200, starts_at=_today_at(12)
    )

    page = client.get("/parent/notices/balance").text
    assert "не хватает" in page
    assert "notice-banner" in page


def test_parent_notice_debt_partial(
    client, owner, student_factory, operation_factory
):
    """Партиал задолженности: пустое тело без долга, текст при долге."""
    contact_id = _logged_in_parent(client, owner)
    # Долгов нет — пустой ответ.
    assert client.get("/parent/notices/debt").text.strip() == ""

    anya = student_factory(tutor_id=owner, first_name="Аня")
    _link(anya, contact_id)
    operation_factory(student_id=anya, kind="lesson", amount=600)

    page = client.get("/parent/notices/debt").text
    assert "Задолженность за прошедшие уроки" in page


def test_parent_notices_require_session(client):
    """Партиалы алертов недоступны без сессии контакта."""
    for url in ("/parent/notices/balance", "/parent/notices/debt"):
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/parent/login"


def test_parent_notice_banner_on_all_pages(client, owner):
    """Контейнер алертов присутствует на всех четырёх страницах родителя."""
    _logged_in_parent(client, owner)
    for url in (
        "/parent/lessons",
        "/parent/homework",
        "/parent/finance",
        "/parent/profile",
    ):
        page = client.get(url).text
        assert 'id="parent-notice-stack"' in page, url
        assert 'hx-get="/parent/notices/balance"' in page, url
        assert 'hx-get="/parent/notices/debt"' in page, url
