"""Главная страница репетитора: дашборд «сегодня» по референсу.

Четыре стат-карточки и два списка («Расписание на сегодня», «Недавние
платежи») считает `app/tutor/services/dashboard.py`; вьюха только
проверяет доступ и складывает контекст. Карточка профиля живёт на
отдельной странице `/tutor/profile` — сайдбар ссылается на неё из футера.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.dashboard import dashboard_context

router = APIRouter()


@router.get("/tutor/", response_class=HTMLResponse)
def home(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Дашборд главной; без сессии — редирект на вход (LoginRequired)."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        raise LoginRequired()

    context = dashboard_context(db, tutor)
    context["tutor"] = tutor
    return templates.TemplateResponse(request, "tutor/home.html", context)
