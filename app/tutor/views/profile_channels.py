"""Каналы уведомлений на вкладке «Уведомления»: привязка мессенджеров.

Блок — HTMX-фрагмент (`#channels-block`): «Подключить» и «Отвязать»
возвращают обновлённый фрагмент целиком, без JS работают 303-редиректом
на вкладку. Проверка привязки — GET того же фрагмента: пока есть
незавершённая привязка, фрагмент опрашивает сам себя (`every 4s`), и
каждый опрос читает апдейты бота — канал привязывается сам, когда
репетитор нажал «Запустить» в чате. GET, который меняет состояние,
оправдан: подтверждение возможно только с одноразовым кодом, сгенерированным
в сессии этого же репетитора, и после успеха идемпотентно (код удаляется),
а htmx-поллинг умеет только GET.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.common.responses import is_htmx
from app.database import get_db
from app.messenger.services.binding import (
    BINDING_FAILED_HINT,
    channels_block_context,
    confirm_binding,
    start_binding,
    unbind_channel,
)
from app.messenger.services.messengers import SUPPORTED
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.profile_page import profile_page_context

router = APIRouter()

_TAB_URL = "/tutor/profile?tab=notifications"

_CHECK_URL = "/tutor/profile/notifications/channels"


@router.get(_CHECK_URL, response_class=HTMLResponse)
def channels_block(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Фрагмент блока: автоопрос незавершённой привязки и ручная «Проверить».

    Каждый запрос проверяет апдейты ботов по всем незавершённым привязкам.
    """
    tutor = _tutor_or_login(db, tutor_id)
    errors = _confirm_pending(db, tutor_id)
    return _channels_response(request, db, tutor, errors)


@router.post(
    "/tutor/profile/notifications/channels/{messenger}/connect",
    response_class=HTMLResponse,
)
def connect_channel(
    request: Request,
    messenger: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Начинает привязку: одноразовый код и диплинк сохраняются."""
    tutor = _tutor_or_login(db, tutor_id)
    _require_supported(messenger)
    errors = start_binding(db, tutor_id, messenger)
    if not is_htmx(request):
        # Без JS фрагмент некуда вставлять: редирект на вкладку, точный
        # текст ошибки не переносится URL'ом — показываем общий hint.
        if errors:
            return RedirectResponse(f"{_TAB_URL}&bind_error=1", status_code=303)
        return RedirectResponse(_TAB_URL, status_code=303)
    return _channels_response(request, db, tutor, errors)


@router.post(
    "/tutor/profile/notifications/channels/{messenger}/unlink",
    response_class=HTMLResponse,
)
def unlink_channel(
    request: Request,
    messenger: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Отвязывает канал: привязка чата и незавершённая привязка удаляются."""
    tutor = _tutor_or_login(db, tutor_id)
    _require_supported(messenger)
    unbind_channel(db, tutor_id, messenger)
    if not is_htmx(request):
        return RedirectResponse(_TAB_URL, status_code=303)
    return _channels_response(request, db, tutor)


def _tutor_or_login(db: Session, tutor_id: str) -> Tutor:
    """Карточка репетитора; сессия указывает на удалённого — входа нет."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()
    return tutor


def _require_supported(messenger: str) -> None:
    """Неизвестный/неподдерживаемый мессенджер — маршрута нет (404)."""
    if messenger not in SUPPORTED:
        raise HTTPException(status_code=404)


def _confirm_pending(db: Session, tutor_id: str) -> list[str]:
    """Подтверждает все незавершённые привязки; ошибки API — списком."""
    errors: list[str] = []
    for messenger in SUPPORTED:
        errors.extend(confirm_binding(db, tutor_id, messenger))
    return errors


def _channels_response(
    request: Request,
    db: Session,
    tutor: Tutor,
    errors: list[str] | None = None,
) -> HTMLResponse:
    """Ответ с обновлённым состоянием каналов: htmx — фрагмент, иначе
    целая страница вкладки (ручная «Проверить» без JS)."""
    context = profile_page_context(
        db,
        tutor,
        tab="notifications",
        errors=errors,
        channels_block=channels_block_context(db, tutor.id, extra_errors=errors),
    )
    if is_htmx(request):
        return templates.TemplateResponse(request, "tutor/_channels_block.html", context)
    return templates.TemplateResponse(request, "tutor/profile.html", context)
