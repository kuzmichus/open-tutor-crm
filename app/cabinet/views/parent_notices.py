"""Плашки-предупреждения кабинета родителя — партиалы `/parent/notices/*`.

Страницы кабинета родителя включают статичный контейнер
`parent/_notice_banner.html`, который сам запрашивает эти эндпоинты
(`hx-trigger="load"`, design D6 — в кабинете родителя нет сохраняющих
событий, поэтому `from:body`-триггеры не нужны); вьюхи страниц данные
плашек в контекст не передают — так же, как у репетитора. Нечего
показывать — пустое тело: контейнер остаётся пустым.

Пути — отдельные от репетиторских `/tutor/notices/*`: сессии разные
(контакт ≠ репетитор), и общий ответ смешал бы данные двух актёров.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import require_contact_id
from app.cabinet.services.children import children
from app.cabinet.services.notices import debt_notice, today_shortfall_notice
from app.database import get_db
from app.student.models.contact import Contact
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/parent/notices/balance", response_class=HTMLResponse)
def parent_balance_notice_partial(
    request: Request,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Плашка нехватки денег на занятия детей сегодня; пусто — без данных."""
    contact = db.get(Contact, contact_id)
    kids = children(db, contact_id)
    tutor = db.get(Tutor, contact.tutor_id)

    notice = today_shortfall_notice(db, tutor, kids)
    if notice is None:
        return HTMLResponse(content="")

    return templates.TemplateResponse(
        request,
        "cabinet/parent/_notice_balance.html",
        {
            "notice": notice,
            # Ключ-состояние для клиентского закрытия: день педагога,
            # состав детей и сумма нехватки (день обязателен — закрытое
            # сегодня напоминание не должно скрывать завтрашний долг).
            "notice_key": "pdebt:"
            + notice["day"].isoformat()
            + ":"
            + "|".join(notice["student_ids"])
            + "#"
            + str(notice["missing"]),
        },
    )


@router.get("/parent/notices/debt", response_class=HTMLResponse)
def parent_debt_notice_partial(
    request: Request,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Плашка задолженности за прошедшие уроки детей; пусто — без долга."""
    contact = db.get(Contact, contact_id)
    kids = children(db, contact_id)

    notice = debt_notice(db, kids)
    if notice is None:
        return HTMLResponse(content="")

    return templates.TemplateResponse(
        request,
        "cabinet/parent/_notice_debt.html",
        {
            "notice": notice,
            # Долг от календарного дня не зависит: состав детей и суммы.
            "notice_key": "ploans:"
            + "|".join(notice["student_ids"])
            + "#"
            + str(notice["total"]),
        },
    )
