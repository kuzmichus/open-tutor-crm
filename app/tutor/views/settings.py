"""Страница настроек мессенджеров (`/tutor/settings`) — GET.

Вкладка выбирается query-параметром (`?tab=messengers`): состояние
живёт в URL, формы работают без JS, на вкладку можно дать ссылку
напрямую. Пока вкладка одна, структура — как у `/tutor/profile`.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.settings_page import settings_page_context

router = APIRouter()


@router.get("/tutor/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    tab: str = "",
    saved: str = "",
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Страница настроек мессенджеров; без сессии — редирект на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        raise LoginRequired()

    context = settings_page_context(
        # «1» — единственное значение, которое шлют редиректы сохранения;
        # bool("0") тоже True: плачку показывал бы любой непустой параметр.
        db, tutor, tab=tab, saved=saved == "1",
    )
    return templates.TemplateResponse(request, "tutor/settings.html", context)
