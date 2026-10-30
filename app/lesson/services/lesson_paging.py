"""Срез страницы списка уроков и ссылки пагинации.

Список отдаётся страницами по `PAGE_SIZE` строк: у репетитора с 24
учениками таблица целиком — 101 строка и семь экранов прокрутки, а
ежедневный сценарий («отметить прошедшие уроки проведёнными») требует
видеть окно целиком (change lessons-table-scale).

Пагинация считается в Python, а не `LIMIT/OFFSET` в SQL: фильтры
(период, статус «не отмеченные», поиск по кириллице) применяются после
выборки — часть из них живёт вне SQL. Поэтому «всего» и «страниц»
известны точно, а лишний запрос за `COUNT` не нужен.

Сервис не знает про FastAPI: на вход — строки и значения query, на
выход — срез и метки для шаблона.
"""

from urllib.parse import urlencode

# Сколько строк на страницу. 50 — компромисс: две трети экрана на ноутбуке
# и ровно один запрос на типичный месяц занятий.
PAGE_SIZE = 50

def normalize_page(page_raw: str, pages: int) -> int:
    """Номер страницы из query, зажатый в [1, pages].

    Мусор в query не должен ломать страницу: неизвестное значение — первая
    страница, номер за пределами — последняя (после смены фильтра список
    короче, и «страница 7 из 2» показывала бы пустоту без выхода).
    """
    try:
        page = int(page_raw)
    except (TypeError, ValueError):
        page = 1
    return min(max(page, 1), pages)


def paginate(
    rows: list[dict], page_raw: str
) -> tuple[list[dict], dict]:
    """Срез страницы и метки пагинации.

    Возвращает `(строки страницы, {"page", "pages", "total", "per_page"})`.
    Пустой список — одна страница: шаблон не должен показывать «страница 1
    из 0».
    """
    total = len(rows)
    pages = max(1, -(-total // PAGE_SIZE))
    page = normalize_page(page_raw, pages)
    start = (page - 1) * PAGE_SIZE
    return (
        rows[start : start + PAGE_SIZE],
        {
            "page": page,
            "pages": pages,
            "total": total,
            "per_page": PAGE_SIZE,
        },
    )


def query_string(**params) -> str:
    """Строка query из переданных параметров без пустых значений.

    Пустые значения не попадают в адрес: `?period=&sort=` в ссылке читается
    как «фильтр выбран, но пустой», а на деле это значение по умолчанию.
    """
    clean = {
        key: value
        for key, value in params.items()
        if value not in (None, "")
    }
    return urlencode(clean)


def page_url(base: str, **params) -> str:
    """Адрес с параметрами выборки; без параметров — сам `base`."""
    query = query_string(**params)
    return f"{base}?{query}" if query else base


def sort_link(base: str, column: str, sort: str, direction: str, **params) -> dict:
    """Ссылка и состояние заголовка колонки.

    Повторный клик по уже выбранной колонке разворачивает порядок; клик по
    другой колонке начинает с возрастания — так «Дата» сразу даёт
    «сначала ближайшие», а «Ученик» — алфавитный порядок.

    `aria_sort` — для скринридера: `ascending` / `descending` у выбранной
    колонки и `none` у остальных (иначе ассистивные технологии читают все
    заголовки как сортированные).
    """
    active = column == sort
    next_direction = "desc" if active and direction == "asc" else "asc"
    return {
        "column": column,
        "active": active,
        "direction": direction if active else "asc",
        "aria_sort": (
            "ascending" if direction == "asc" else "descending"
        ) if active else "none",
        "url": page_url(
            base, sort=column, direction=next_direction, page="", **params
        ),
    }
