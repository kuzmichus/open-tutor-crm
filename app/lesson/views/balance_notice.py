"""Плашка «сегодня занятие, а на счёте не хватает денег» — партиал кабинета.

Страницы кабинета включают статичный контейнер `_notice_banner.html`,
который сам запрашивает этот эндпоинт (`hx-trigger="load"`); вьюхи страниц
данные плашки в контекст не передают — так же, как у напоминания о не
отмеченных уроках. Нечего показывать (уроков нет или денег хватает) —
пустое тело: контейнер остаётся пустым.

Путь `/tutor/notices/balance` — отдельный от `/tutor/notices`: два баннера
независимы (деньги и не отмеченные уроки), и общий ответ смешал бы их
ключи закрытия.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.lesson.services.balance_notice import today_balance_notice
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/notices/balance", response_class=HTMLResponse)
def balance_notice_partial(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Плашка нехватки денег; без сессии — редирект на вход (LoginRequired)."""
    tutor = db.get(Tutor, tutor_id)
    notice = today_balance_notice(db, tutor)
    if notice is None:
        # Пустое тело, а не «всё оплачено»: контейнеру нечего показывать.
        return HTMLResponse(content="")

    return templates.TemplateResponse(
        request,
        "lesson/_balance_notice.html",
        {
            "notice": notice,
            # Ключ-состояние для клиентского закрытия: состав учеников и
            # сумма нехватки. Частичная оплата меняет сумму — плашка
            # возвращается; полная оплата убирает её вовсе (сервер не
            # рендерит разметку).
            "notice_key": "debt:"
            + "|".join(notice["student_ids"])
            + "#"
            + str(notice["missing"]),
            "tutor": tutor,
        },
    )
