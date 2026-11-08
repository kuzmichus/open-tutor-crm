"""Редактор лендинга: загрузка черновика и сохранение правок.

`GET /tutor/landing/editor` отдаёт автономную страницу с GrapesJS:
в документ вшиваются тело и первый `<style>` текущего черновика, а скрипты
из тела вырезаются — в редакторе им не место, `landing-auth.js` вернётся
при сохранении. Если черновика ещё нет, он создаётся из шаблона профиля
(как кнопка «Создать черновик» на странице управления).

`POST /tutor/landing/draft` принимает `{html, css}` от `editor.getHtml()` /
`editor.getCss()`, собирает полный документ (`draft_render.py`) и пишет его
в `draft.html`. `<title>` сохраняется из текущего черновика, тег
`landing-auth.js` гарантируется идемпотентно.

Фича доступна только в сингл-режиме: каждый роут начинается с
`_ensure_landing_enabled()` и в мульти-режиме отвечает 404 — до любого
обращения к диску. `tutor_id` берётся только из сессии.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.common.access import LoginRequired, require_tutor_id
from app.database import get_db
from app.landing.services.access import landing_enabled
from app.landing.services.draft_render import (
    extract_body,
    extract_first_style,
    render_draft_document,
    strip_scripts,
)
from app.landing.services.storage import get_storage
from app.landing.services.template import save_default_draft
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

EDITOR_URL = "/tutor/landing/editor"
DRAFT_URL = "/tutor/landing/draft"


class DraftPayload(BaseModel):
    """Тело запроса сохранения: HTML и CSS из GrapesJS."""

    html: str = ""
    css: str = ""


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


@router.get(EDITOR_URL, response_class=HTMLResponse)
def landing_editor(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Полноэкранный редактор с текущим черновиком (или новым из профиля)."""
    _ensure_landing_enabled()
    tutor = _tutor_or_login(db, tutor_id)

    storage = get_storage()
    draft_html = storage.read_draft_html()
    if draft_html is None:
        draft_html = save_default_draft(tutor)

    response = templates.TemplateResponse(
        request,
        "landing/editor.html",
        {
            "tutor": tutor,
            "draft": {
                "body": strip_scripts(extract_body(draft_html)),
                "css": extract_first_style(draft_html),
            },
        },
    )
    # Черновик меняется после каждого сохранения: страница редактора не
    # должна показывать старую версию из кэша.
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post(DRAFT_URL)
def landing_save_draft(
    payload: DraftPayload,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> JSONResponse:
    """Собирает полный документ из HTML/CSS редактора и пишет черновик."""
    _ensure_landing_enabled()
    tutor = _tutor_or_login(db, tutor_id)

    storage = get_storage()
    document = render_draft_document(
        tutor,
        html=payload.html,
        css=payload.css,
        existing_html=storage.read_draft_html(),
    )
    storage.save_draft(document)
    return JSONResponse(
        {"message": "Сохранено"},
        headers={"Cache-Control": "no-store"},
    )
