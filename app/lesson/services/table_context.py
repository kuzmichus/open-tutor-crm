"""Контекст таблицы уроков: один для страницы и для htmx-партиала.

Страница `/tutor/lessons` и партиал `/tutor/lessons/list` показывают одну и
ту же таблицу, поэтому и контекст собирается здесь: если бы каждая вьюха
считала его сама, сортировка и пагинация разъехались бы между полной
загрузкой и фильтрацией (change lessons-table-scale).

Сервис не знает про FastAPI: на вход — `Session`, значения query и
карточка владельца, на выход — словарь для шаблона.
"""

from sqlalchemy.orm import Session

from app.lesson.services.lesson_paging import (
    page_url,
    paginate,
    sort_link,
)
from app.lesson.services.lessons import (
    list_lessons,
    normalize_direction,
    normalize_period,
    normalize_sort,
    normalize_status,
)

LESSONS_URL = "/tutor/lessons"

# Колонки таблицы: ключ → подпись и признак сортировки.
# «Стоимость» и «Оценка» не сортируются: у групповых уроков стоимости нет,
# а оценка пуста у всех непроведённых — порядок по ним читался бы как шум.
# Порядок колонок — порядок в спеке lesson-management («Список уроков»).
COLUMNS = (
    ("target", "Ученик / Группа", True),
    ("date", "Дата и время", True),
    ("price", "Стоимость", False),
    ("rating", "Оценка", False),
    ("status", "Статус", True),
)


def table_context(
    db: Session,
    tutor_id: str,
    tutor,
    *,
    q: str = "",
    period: str = "",
    status: str = "",
    student_id: str = "",
    sort: str = "date",
    direction: str = "asc",
    page: str = "",
    student_options: list | None = None,
) -> dict:
    """Контекст таблицы: строки страницы, пагинация, заголовки сортировки.

    `q`/`period`/`status`/`student_id` нормализуются здесь, а не во вьюхах:
    мусор в query должен одинаково схлопываться и на странице, и в
    партиале.
    """
    q = q.strip()
    period = normalize_period(period)
    status = normalize_status(status)
    sort = normalize_sort(sort)
    direction = normalize_direction(direction)

    rows = list_lessons(
        db,
        tutor_id,
        q=q,
        period=period,
        status=status,
        student_id=student_id,
        sort=sort,
        direction=direction,
        tutor=tutor,
    )
    page_rows, paging = paginate(rows, page)

    # Параметры выборки без страницы: их переносят и пагинация, и сортировка,
    # чтобы клик по заголовку не сбрасывал фильтры.
    base_params = {
        "q": q,
        "period": period,
        "status": status,
        "student": student_id,
        "sort": sort,
        "direction": direction,
    }

    return {
        "rows": page_rows,
        "total": paging["total"],
        "tutor": tutor,
        "paging": {
            **paging,
            "prev_url": page_url(
                LESSONS_URL, **{**base_params, "page": paging["page"] - 1}
            )
            if paging["page"] > 1
            else None,
            "next_url": page_url(
                LESSONS_URL, **{**base_params, "page": paging["page"] + 1}
            )
            if paging["page"] < paging["pages"]
            else None,
        },
        "columns": [
            {
                "key": key,
                "label": label,
                "sortable": sortable,
                **(
                    sort_link(
                        LESSONS_URL,
                        key,
                        sort,
                        direction,
                        q=q,
                        period=period,
                        status=status,
                        student=student_id,
                    )
                    if sortable
                    else {"aria_sort": None, "url": None, "active": False}
                ),
            }
            for key, label, sortable in COLUMNS
        ],
        "sort": sort,
        "direction": direction,
        "q": q,
        "period": period,
        "status": status,
        "student_id": student_id,
        "student_options": student_options or [],
    }
