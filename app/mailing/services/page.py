"""Вкладки страницы «Коммуникации»: список, разбор query и ссылки.

Паттерн вкладок финансов: состояние в адресе (`?tab=`), htmx-ручка
`/tutor/mailings/tabs/{tab}` возвращает секцию с `HX-Push-Url`. У вкладки
два адреса — `href` открывает страницу целиком (без JS), `url` — ручку
партиала.
"""

from sqlalchemy.orm import Session

from app.mailing.services.compose import compose_context
from app.mailing.services.history import HISTORY_LIMIT, list_history

TAB_COMPOSE = "compose"
TAB_HISTORY = "history"

TABS = (
    {"key": TAB_COMPOSE, "label": "Новое сообщение", "icon": "send"},
    {"key": TAB_HISTORY, "label": "История", "icon": "history"},
)


def normalize_tab(raw: str) -> str:
    """Вкладка из query/пути; неизвестное значение — «Новое сообщение»."""
    return TAB_HISTORY if raw == TAB_HISTORY else TAB_COMPOSE


def page_url(tab: str) -> str:
    """Канонический адрес вкладки для `HX-Push-Url` (без мусора в query)."""
    if normalize_tab(tab) == TAB_HISTORY:
        return "/tutor/mailings?tab=history"
    return "/tutor/mailings"


def tabs_context(tab: str) -> dict:
    """Ссылки вкладок с признаком активности."""
    chosen = normalize_tab(tab)
    items = []
    for item in TABS:
        items.append(
            {
                **item,
                "active": item["key"] == chosen,
                "href": page_url(item["key"]),
                "url": f"/tutor/mailings/tabs/{item['key']}",
            }
        )
    return {"tabs": items}


def tab_context(db: Session, tutor_id: str, tab: str, *, q: str, segment: str) -> dict:
    """Контекст содержимого вкладки (общий для страницы и htmx-ручки)."""
    chosen = normalize_tab(tab)
    context = {"tab": chosen}
    if chosen == TAB_HISTORY:
        context["history_rows"] = list_history(db, tutor_id)
        context["history_limit"] = HISTORY_LIMIT
    else:
        context.update(compose_context(db, tutor_id, q=q, segment=segment))
    return context
