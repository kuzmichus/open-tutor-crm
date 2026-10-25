"""Баннер-напоминание «N уроков не отмечены» — партиал для всех страниц кабинета.

Страницы кабинета включают статичный контейнер `_notice_banner.html`, который
сам запрашивает этот эндпоинт (`hx-trigger="load"`); вьюхи страниц баннер в
контекст не передают (design D1 change'а unmarked-lessons). Нет не отмеченных
уроков — пустое тело: контейнер остаётся пустым. `?explain=1` добавляет строку
пояснения — её запрашивает только контейнер главной страницы.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.lesson.services.unmarked import list_unmarked
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/notices", response_class=HTMLResponse)
def notices_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Плашка напоминания; без сессии — редирект на вход (LoginRequired)."""
    tutor = db.get(Tutor, tutor_id)
    rows = list_unmarked(db, tutor_id, tutor)
    if not rows:
        # Пустое тело, а не «всё хорошо»: контейнеру нечего показывать.
        return HTMLResponse(content="")

    return templates.TemplateResponse(
        request,
        "lesson/_notices.html",
        {
            "rows": rows,
            # Ключ-состояние для клиентского закрытия: состав уроков.
            # Изменился состав (новый не отмеченный урок) — ключ другой,
            # и закрытая ранее плашка возвращается.
            "notice_key": "|".join(str(row["lesson"].id) for row in rows),
            "latest": rows[0],
            "explain": request.query_params.get("explain") == "1",
            "tutor": tutor,
        },
    )
