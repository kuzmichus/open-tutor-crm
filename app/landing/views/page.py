"""Управляющая страница лендинга: статус, предпросмотр и действия.

`GET /tutor/landing` — единственная точка входа репетитора в лендинг.
Страница показывает состояние (опубликован / черновик / пусто), открывает
предпросмотр черновика и выполняет действия: опубликовать, снять с
публикации, вернуть шаблон из профиля.

Фича доступна только в сингл-режиме: каждый роут начинается с
`_ensure_landing_enabled()` и в мульти-режиме отвечает 404 — до любого
обращения к диску. Проверка стоит и на POST: иначе страницу можно было бы
опубликовать прямым запросом в обход интерфейса.

`tutor_id` берётся только из сессии (`require_tutor_id`), поэтому чужие
данные в шаблон и на диск не попадают. Полноэкранный редактор живёт в
отдельном роутере (`app/landing/views/editor.py`), кнопка «Редактировать»
ведёт на `/tutor/landing/editor`.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.landing.services.access import landing_enabled
from app.landing.services.storage import get_storage
from app.landing.services.template import (
    STATUS_PUBLISHED,
    page_state,
    save_default_draft,
)
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

LANDING_URL = "/tutor/landing"

# Плашки после действий: `?status=` — значение из редиректа, текст — то,
# что видит репетитор. Неизвестное значение не показывает ничего.
_STATUS_MESSAGES = {
    STATUS_PUBLISHED: "Страница опубликована — она открывается на главной.",
    "unpublished": "Страница снята с публикации.",
    "reset": "Черновик создан заново из профиля.",
    "no-draft": "Черновика пока нет — сначала создайте его из профиля.",
}

# «no-draft» — не успех, а подсказка: показываем как ошибку.
_ERROR_STATUSES = frozenset({"no-draft"})


def _ensure_landing_enabled() -> None:
    """404 в мульти-режиме: фича существует только в сингл-установке."""
    if not landing_enabled():
        raise HTTPException(status_code=404)


def _tutor_or_login(db: Session, tutor_id: str) -> Tutor:
    """Репетитор из сессии; удалённый аккаунт — как отсутствие входа."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()
    return tutor


@router.get(LANDING_URL, response_class=HTMLResponse)
def landing_page(
    request: Request,
    status: str = "",
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Страница управления лендингом: состояние и действия."""
    _ensure_landing_enabled()
    tutor = _tutor_or_login(db, tutor_id)

    state = page_state(get_storage())
    message = _STATUS_MESSAGES.get(status, "")

    return templates.TemplateResponse(
        request,
        "landing/page.html",
        {
            "active_page": "landing",
            "user_name": tutor.name,
            "user_role": "Владелец",
            "tutor": tutor,
            "page": state,
            "message": message,
            "message_is_error": status in _ERROR_STATUSES,
        },
    )


@router.get(f"{LANDING_URL}/preview", response_class=FileResponse)
def landing_preview() -> FileResponse:
    """Черновик как есть; нет черновика — 404."""
    _ensure_landing_enabled()
    path = get_storage().draft_path
    if not path.is_file():
        raise HTTPException(status_code=404)
    # Черновик меняется при каждой правке, поэтому браузер обязан
    # сверять его с сервером, как и опубликованную страницу с `/`.
    return FileResponse(
        path,
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


@router.post(f"{LANDING_URL}/publish")
def landing_publish(
    tutor_id: str = Depends(require_tutor_id),
) -> RedirectResponse:
    """Публикует черновик; публиковать нечего — подсказка, а не ошибка."""
    _ensure_landing_enabled()
    published = get_storage().publish()
    status = STATUS_PUBLISHED if published else "no-draft"
    return RedirectResponse(
        url=f"{LANDING_URL}?status={status}", status_code=303
    )


@router.post(f"{LANDING_URL}/unpublish")
def landing_unpublish(
    tutor_id: str = Depends(require_tutor_id),
) -> RedirectResponse:
    """Снимает страницу с публикации, не трогая черновик и бэкап."""
    _ensure_landing_enabled()
    get_storage().unpublish()
    return RedirectResponse(
        url=f"{LANDING_URL}?status=unpublished", status_code=303
    )


@router.post(f"{LANDING_URL}/reset")
def landing_reset(
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> RedirectResponse:
    """Перезаписывает черновик шаблоном из профиля (или создаёт первый)."""
    _ensure_landing_enabled()
    tutor = _tutor_or_login(db, tutor_id)
    save_default_draft(tutor)
    return RedirectResponse(url=f"{LANDING_URL}?status=reset", status_code=303)
