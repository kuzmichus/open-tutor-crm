"""Масштабирование таблицы уроков: сортировка, пагинация, массовая отметка.

Change `2026-10-27-lessons-table-scale`. Проверяется HTTP-путём — те же
маршруты и поля формы, что у пользователя (правило AGENTS.md): ссылки
сортировки и пагинации читаются из разметки, массовая отметка идёт POST'ом
с повторяющимся полем `lesson_id`.

Списания проверяются здесь же: массовая отметка меняет статус урока, а
списание — производная от статуса (design D6 спеки finance). Пропущенная
синхронизация оставила бы урок «Проведён» с пустым счётом.
"""

import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.lesson.models.lesson import Lesson
from app.lesson.services.lesson_paging import PAGE_SIZE
from app.student.models.student import Student

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="lessons-scale@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "lessons-scale@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _insert_lesson(tutor_id: str, **overrides) -> str:
    """Урок напрямую в БД; возвращает id (странице нужна только строка)."""
    with SessionLocal() as db:
        if "student_id" not in overrides and "group_id" not in overrides:
            student = db.query(Student).filter_by(tutor_id=tutor_id).first()
            overrides["student_id"] = student.id
        overrides.setdefault("type", "individual")
        overrides.setdefault("starts_at", datetime(2026, 10, 19, 10, 0))
        overrides.setdefault("duration_min", 60)
        overrides.setdefault("status", "planned")
        lesson = Lesson(**overrides)
        db.add(lesson)
        db.commit()
        return str(lesson.id)


def _ids(page: str) -> list[str]:
    """Id уроков в порядке их появления в таблице."""
    return re.findall(r'lessons-table__row" id="lesson-row-([^"]+)"', page)


def _lesson_status(lesson_id: str) -> str:
    with SessionLocal() as db:
        return db.get(Lesson, lesson_id).status


def _charges(lesson_id: str) -> list[AccountOperation]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AccountOperation).where(
                    AccountOperation.lesson_id == lesson_id
                )
            ).all()
        )


# --------------------------------------------------------------------------
# Сортировка (спека lesson-management, «Фильтры, поиск и сортировка»)
# --------------------------------------------------------------------------


def test_sort_by_target_orders_rows_by_name(owner, client, student_factory):
    """Клик по «Ученик / Группа» сортирует по имени цели, повторный — назад."""
    anna = student_factory(tutor_id=owner, first_name="Анна")
    yana = student_factory(tutor_id=owner, first_name="Яна")
    first = _insert_lesson(owner, student_id=yana, starts_at=datetime(2026, 10, 19, 9, 0))
    second = _insert_lesson(owner, student_id=anna, starts_at=datetime(2026, 10, 19, 11, 0))

    ascending = _ids(client.get("/tutor/lessons", params={"sort": "target"}).text)
    assert ascending == [second, first]  # Анна раньше Яны

    descending = _ids(
        client.get(
            "/tutor/lessons", params={"sort": "target", "direction": "desc"}
        ).text
    )
    assert descending == [first, second]


def test_sort_by_target_ignores_case_for_cyrillic(owner, client, student_factory):
    """`lower()` SQLite не знает кириллицу — ключ считается в Python.

    Без `casefold` заглавные буквы уехали бы в начало списка отдельной
    группой, и алфавитный порядок читался бы как поломанный.
    """
    lower = student_factory(tutor_id=owner, first_name="анна")
    upper = student_factory(tutor_id=owner, first_name="Борис")
    first = _insert_lesson(owner, student_id=upper, starts_at=datetime(2026, 10, 19, 9, 0))
    second = _insert_lesson(owner, student_id=lower, starts_at=datetime(2026, 10, 19, 11, 0))

    order = _ids(client.get("/tutor/lessons", params={"sort": "target"}).text)
    assert order == [second, first]


def test_sort_by_status_uses_model_order(owner, client, student_factory):
    """Статус сортируется по порядку списка модели, а не по алфавиту."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    completed = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0),
        status="completed",
    )
    planned = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 11, 0),
        status="planned",
    )

    order = _ids(client.get("/tutor/lessons", params={"sort": "status"}).text)
    # «Запланирован» раньше «Проведён»: сначала то, что ещё не сделано.
    assert order == [planned, completed]


def test_sort_header_is_link_and_keeps_filters(owner, client, student_factory):
    """Заголовок — ссылка, несущая текущие фильтры, и `aria-sort`."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_lesson(owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0))

    page = client.get("/tutor/lessons", params={"student": student}).text

    link = re.search(
        r'<a class="lessons-table__sort[^"]*"\s+href="([^"]+)"', page
    )
    assert link, "в шапке нет ссылки сортировки"
    url = link.group(1)
    assert "sort=" in url
    # Фильтр по ученику не сбрасывается переключением порядка.
    assert f"student={student}" in url
    assert 'aria-sort="ascending"' in page


def test_sort_direction_flips_on_active_column(owner, client, student_factory):
    """Повторный клик по выбранной колонке ведёт на обратное направление."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_lesson(owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0))

    page = client.get(
        "/tutor/lessons", params={"sort": "date", "direction": "asc"}
    ).text

    link = re.search(
        r'<a class="lessons-table__sort lessons-table__sort--active"\s+href="([^"]+)"',
        page,
    )
    assert link, "выбранная колонка не помечена активной"
    assert "direction=desc" in link.group(1)
    assert 'aria-sort="ascending"' in page


def test_unknown_sort_falls_back_to_date(owner, client, student_factory):
    """Мусор в `sort`/`direction` — порядок по умолчанию, без ошибки."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    later = _insert_lesson(owner, student_id=student, starts_at=datetime(2026, 10, 20, 9, 0))
    earlier = _insert_lesson(owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0))

    response = client.get(
        "/tutor/lessons", params={"sort": "bogus", "direction": "sideways"}
    )
    assert response.status_code == 200
    assert _ids(response.text) == [earlier, later]


def test_unsortable_columns_are_plain_text(owner, client, student_factory):
    """«Стоимость» и «Оценка» не сортируются — в шапке нет ссылки."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_lesson(owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0))

    page = client.get("/tutor/lessons").text

    head = re.search(r"<thead>.*?</thead>", page, re.S)
    assert head
    headers = re.findall(r"<th[^>]*>(.*?)</th>", head.group(0), re.S)
    cost = next(cell for cell in headers if "Стоимость" in cell)
    rating = next(cell for cell in headers if "Оценка" in cell)
    assert "lessons-table__sort" not in cost
    assert "lessons-table__sort" not in rating


# --------------------------------------------------------------------------
# Пагинация (спека lesson-management, «Пагинация списка уроков»)
# --------------------------------------------------------------------------


def _insert_many(owner: str, student: str, count: int) -> list[str]:
    """`count` уроков с разным временем начала; возвращает id по порядку.

    Время разное намеренно: у уроков с одинаковым `starts_at` порядок
    задаёт вторичный ключ `id`, и «остаток на второй странице» был бы
    непредсказуем — тест проверял бы генератор uuid, а не пагинацию.
    """
    return [
        _insert_lesson(
            owner,
            student_id=student,
            starts_at=datetime(2026, 10, 1, 0, 0) + timedelta(hours=index),
            duration_min=30,
        )
        for index in range(count)
    ]


def test_first_page_holds_page_size_rows(owner, client, student_factory):
    """На странице не больше `PAGE_SIZE` строк, счётчик говорит «из 2»."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_many(owner, student, PAGE_SIZE + 3)

    page = client.get("/tutor/lessons").text

    assert len(_ids(page)) == PAGE_SIZE
    assert f"Всего: {PAGE_SIZE + 3}" in page
    assert "страница 1 из 2" in page
    # «Назад» на первой странице — не ссылка.
    assert ">Назад</a>" not in page
    assert ">Вперёд</a>" in page


def test_second_page_shows_rest(owner, client, student_factory):
    """Вторая страница — остаток, «Вперёд» становится неактивным."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    ids = _insert_many(owner, student, PAGE_SIZE + 3)

    page = client.get("/tutor/lessons", params={"page": "2"}).text

    shown = _ids(page)
    assert len(shown) == 3
    # Остаток — последние по времени начала.
    assert shown == ids[-3:] or set(shown) == set(ids[-3:])
    assert "страница 2 из 2" in page
    assert ">Вперёд</a>" not in page


def test_page_links_keep_filters_and_sort(owner, client, student_factory):
    """Ссылка пагинации несёт фильтры и порядок, иначе они терялись бы."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_many(owner, student, PAGE_SIZE + 1)

    page = client.get(
        "/tutor/lessons",
        params={"student": student, "sort": "status", "direction": "desc"},
    ).text

    link = re.search(r'href="([^"]*page=2[^"]*)"', page)
    assert link, "нет ссылки на вторую страницу"
    url = link.group(1)
    assert f"student={student}" in url
    assert "sort=status" in url
    assert "direction=desc" in url


def test_page_out_of_range_lands_on_last(owner, client, student_factory):
    """`page=99` при двух страницах — последняя, а не пустота."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_many(owner, student, PAGE_SIZE + 1)

    response = client.get("/tutor/lessons", params={"page": "99"})

    assert response.status_code == 200
    assert len(_ids(response.text)) == 1
    assert "страница 2 из 2" in response.text


def test_garbage_page_shows_first(owner, client, student_factory):
    """Мусор в `page` — первая страница, без ошибки 500."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_lesson(owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0))

    response = client.get("/tutor/lessons", params={"page": "abc"})

    assert response.status_code == 200
    assert len(_ids(response.text)) == 1


def test_empty_list_has_single_page(owner, client):
    """Пустой список — одна страница: «страница 1 из 0» не показывается."""
    page = client.get("/tutor/lessons").text

    assert "Уроков пока нет" in page
    assert "страница 1 из 0" not in page


# --------------------------------------------------------------------------
# Массовая отметка (спека lesson-management, «Массовая отметка уроков»)
# --------------------------------------------------------------------------


def test_bulk_complete_marks_selected_lessons(owner, client, student_factory):
    """Два выбранных урока становятся «Проведён», по каждому — списание."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    first = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0), price=1200
    )
    second = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 20, 9, 0), price=1500
    )
    untouched = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 21, 9, 0), price=1000
    )

    response = client.post(
        "/tutor/lessons/complete-selected",
        data={"lesson_id": [first, second]},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "lesson-saved"
    assert _lesson_status(first) == "completed"
    assert _lesson_status(second) == "completed"
    assert _lesson_status(untouched) == "planned"
    # Списание — производная от статуса: сумма равна цене урока.
    assert [charge.amount for charge in _charges(first)] == [1200]
    assert [charge.amount for charge in _charges(second)] == [1500]
    assert _charges(untouched) == []


def test_bulk_complete_skips_already_completed(owner, client, student_factory):
    """Проведённый урок не пересчитывается: второе списание не создаётся."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    done = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0),
        price=1200, status="completed",
    )
    planned = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 20, 9, 0), price=900
    )
    # Списание у проведённого урока создаём штатным путём: тест проверяет
    # не «есть ли списание», а «не появилось ли второе» и «не изменилась
    # ли сумма» после повторной отметки.
    with SessionLocal() as db:
        from app.finance.services.charges import sync_lesson_charge

        sync_lesson_charge(db, db.get(Lesson, done))
        db.commit()

    client.post(
        "/tutor/lessons/complete-selected",
        data={"lesson_id": [done, planned]},
        headers=HTMX,
    )

    assert _lesson_status(done) == "completed"
    assert _lesson_status(planned) == "completed"
    assert [charge.amount for charge in _charges(done)] == [1200]
    assert [charge.amount for charge in _charges(planned)] == [900]


def test_bulk_complete_ignores_foreign_lesson(
    owner, client, tutor_factory, student_factory
):
    """Чужой id не меняет урок и не раскрывает его существование."""
    other = tutor_factory(email="lessons-scale-other@example.com")
    foreign_student = student_factory(tutor_id=other, first_name="Чужой")
    foreign = _insert_lesson(
        other, student_id=foreign_student, starts_at=datetime(2026, 10, 19, 9, 0),
        price=1200,
    )

    response = client.post(
        "/tutor/lessons/complete-selected",
        data={"lesson_id": [foreign]},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert _lesson_status(foreign) == "planned"
    assert _charges(foreign) == []


def test_bulk_complete_without_selection_changes_nothing(
    owner, client, student_factory
):
    """Пустая отправка — не ошибка: список просто остаётся прежним."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    lesson = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0)
    )

    response = client.post(
        "/tutor/lessons/complete-selected", data={}, headers=HTMX
    )

    assert response.status_code == 200
    assert _lesson_status(lesson) == "planned"


def test_bulk_complete_without_js_redirects(owner, client, student_factory):
    """Без `HX-Request` — 303 на список: форма работает без JS."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    lesson = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0)
    )

    response = client.post(
        "/tutor/lessons/complete-selected",
        data={"lesson_id": [lesson]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/lessons"
    assert _lesson_status(lesson) == "completed"


def test_bulk_complete_requires_session(client, tutor_factory, student_factory):
    """Без входа уроки не меняются: редирект на вход (спека, «Доступ»)."""
    tutor = tutor_factory(email="lessons-scale-anon@example.com")
    student = student_factory(tutor_id=tutor, first_name="Мария")
    lesson = _insert_lesson(
        tutor, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0)
    )

    response = client.post(
        "/tutor/lessons/complete-selected",
        data={"lesson_id": [lesson]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert _lesson_status(lesson) == "planned"


# --------------------------------------------------------------------------
# Разметка и клиентская часть
# --------------------------------------------------------------------------


def test_table_has_checkboxes_and_bulk_button(owner, client, student_factory):
    """Строки несут чекбоксы, над таблицей — «выбрать все», под ней — действие."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    planned = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0)
    )
    done = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 20, 9, 0),
        status="completed",
    )

    page = client.get("/tutor/lessons").text

    assert 'data-lessons-select-all' in page
    assert f'value="{planned}"' in page
    assert 'data-lessons-complete' in page
    assert "Отметить выбранные проведёнными" in page
    # Проведённый урок отметить нечего: его чекбокс выключен.
    done_row = re.search(
        rf'id="lesson-row-{re.escape(done)}".*?</tr>', page, re.S
    ).group(0)
    assert "disabled" in done_row


def test_bulk_form_works_without_js(owner, client, student_factory):
    """Форма вокруг таблицы — обычный POST на статический маршрут."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_lesson(owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0))

    page = client.get("/tutor/lessons").text

    assert 'action="/tutor/lessons/complete-selected"' in page
    assert 'method="post"' in page
    assert 'name="lesson_id"' in page


def test_bulk_selection_script_is_in_lessons_js():
    """Выбор строк живёт в lessons.js и переживает htmx-своп таблицы.

    Обработчики делегированы на документ: таблица подменяется после каждого
    фильтра, и подписки на её узлы умирали бы вместе с ней.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    script = (root / "app" / "static" / "lessons.js").read_text(encoding="utf-8")

    assert "syncBulkSelection" in script
    assert "[data-lessons-select-all]" in script
    assert "[data-lesson-select]" in script


# --------------------------------------------------------------------------
# Регрессии, найденные в браузере при проверке change'а
# --------------------------------------------------------------------------


def test_row_click_ignores_checkbox_target(owner, client, student_factory):
    """Клик по цели чекбокса не открывает модалку строки.

    Строка ловит клик целиком (`hx-get` на `<tr>`), и гасить всплытие из
    `document` бесполезно: обработчик htmx висит на самой строке и
    срабатывает раньше. Поэтому выбор строки исключён фильтром триггера —
    декларативно, на той же строке.
    """
    student = student_factory(tutor_id=owner, first_name="Мария")
    lesson = _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0)
    )

    page = client.get("/tutor/lessons").text
    row_tag = re.search(
        rf"<tr[^>]*id=\"lesson-row-{re.escape(lesson)}\"[^>]*>", page
    )
    assert row_tag, "нет строки урока"
    tag = row_tag.group(0)
    assert "hx-trigger=" in tag
    assert "lessons-select-hit" in tag
    # Чекбокс обёрнут в цель 44×44: клик по её краю тоже не открывает модалку.
    assert '<label class="lessons-select-hit">' in page


def test_header_columns_match_row_cells(owner, client, student_factory):
    """Шапка и строки совпадают по числу и порядку колонок.

    Проверка «Статус»/«Стоимость» не на своих местах: при сборке шапки из
    `COLUMNS` остались дописанные вручную «Стоимость» и «Оценка», и колонок
    стало восемь против шести ячеек — значения вставали под чужими
    заголовками (найдено в браузере).
    """
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_lesson(
        owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0),
        price=1200, status="planned",
    )

    page = client.get("/tutor/lessons").text
    head = re.search(r"<thead>.*?</thead>", page, re.S).group(0)
    body = re.search(r"<tbody>.*?</tbody>", page, re.S).group(0)

    labels = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip().upper()
        for cell in re.findall(r"<th[^>]*>(.*?)</th>", head, re.S)
    ]
    # Первая колонка — выбор строк, у неё нет текстового заголовка.
    assert labels == [
        "",
        "УЧЕНИК / ГРУППА",
        "ДАТА И ВРЕМЯ",
        "СТОИМОСТЬ",
        "ОЦЕНКА",
        "СТАТУС",
    ], labels

    cells = re.findall(r"<td[^>]*>", body)
    assert len(cells) == len(labels), (
        f"ячеек {len(cells)}, колонок {len(labels)} — значения встанут "
        "под чужими заголовками"
    )


def test_table_container_disinherits_include(owner, client, student_factory):
    """Контейнер таблицы гасит наследование `hx-include` для потомков.

    Без `hx-disinherit` ссылки сортировки и пагинации наследовали
    `hx-include="#lessons-filters"` и добавляли параметры фильтров к своему
    полному адресу: каждый клик задваивал `?q=&q=&student=&student=…`
    (найдено в браузере). Атрибут обязан стоять на предке — на самом
    элементе htmx его игнорирует.
    """
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_lesson(owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0))

    page = client.get("/tutor/lessons").text

    container = re.search(r'<div id="lessons-table"[^>]*>', page)
    assert container, "нет контейнера таблицы"
    assert 'hx-disinherit="hx-include"' in container.group(0)
    assert 'hx-include="#lessons-filters"' in container.group(0)


def test_bulk_actions_sit_above_table(owner, client, student_factory):
    """Кнопка массовой отметки — над таблицей, а не под 50 строками.

    Внизу она оказывалась в конце прокрутки: педагог отмечал уроки вверху
    и не видел действия (найдено в браузере).
    """
    student = student_factory(tutor_id=owner, first_name="Мария")
    _insert_lesson(owner, student_id=student, starts_at=datetime(2026, 10, 19, 9, 0))

    page = client.get("/tutor/lessons").text

    actions = page.index('class="lessons-bulk__actions"')
    table = page.index('class="lessons-table-wrap"')
    assert actions < table, "панель действий должна идти до таблицы"

