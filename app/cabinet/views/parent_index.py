"""Адрес `/parent` кабинета родителя: редирект на общую страницу «Уроки».

Страница-хаб с карточками-секциями удалена (change
parent-cabinet-unified-pages, design D2 — решение владельца: редирект);
путь сохранён, потому что ссылки родителям уже разосланы.

Проверка сессии здесь не нужна: страница данных не отдаётся, а без
сессии посетителя всё равно встретит редирект на `/parent/login` на
странице «Уроки».
"""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/parent")
def parent_index() -> RedirectResponse:
    """303 на «Уроки» — общую страницу всех детей."""
    return RedirectResponse(url="/parent/lessons", status_code=303)
