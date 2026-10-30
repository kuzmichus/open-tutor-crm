"""Страница настроек репетитора (`/tutor/profile`) — четыре вкладки.

Вкладка выбирается query-параметром (`?tab=security`): состояние живёт
в URL, формы работают без JS, а ссылку на вкладку можно дать напрямую.
Редактирования карточки и настроек — в соседних POST-роутах.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.messenger.services.binding import BINDING_FAILED_HINT, channels_block_context
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.profile_page import profile_page_context

router = APIRouter()


@router.get("/tutor/profile", response_class=HTMLResponse)
def profile(
    request: Request,
    tab: str = "",
    saved: str = "",
    bind_error: str = "",
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Страница настроек; без сессии — редирект на вход (LoginRequired)."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        raise LoginRequired()

    context = profile_page_context(
        # «1» — единственное значение, которое шлют редиректы сохранения;
        # bool("0") тоже True: плашку показывал бы любой непустой параметр.
        db, tutor, tab=tab, saved=saved == "1",
        # Действия каналов без JS ошибку фрагментом не покажут — общий
        # hint доносится через query-параметр их 303-редиректа.
        channels_block=(
            channels_block_context(db, tutor.id, extra_errors=[BINDING_FAILED_HINT])
            if bind_error
            else None
        ),
    )
    return templates.TemplateResponse(request, "tutor/profile.html", context)
