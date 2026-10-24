"""Вкладка «Платежи» — фрагмент, который перезапрашивает себя (design D11).

Панель приходит и при открытии карточки (включением из формы ученика), и
по событиям, которые меняют счёт: `payment-saved` после платежа/правки/
возврата и прямой POST пересчёта. Поэтому у неё отдельный HTML-эндпоинт,
а не данные, встроенные в форму: DOM обновляется с сервера, а не руками
в JS (правило AGENTS.md).

Как и остальные вкладки, панель требует сессии: чужой ученик и
несуществующий неразличимы — 404.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import get_owned_student, require_tutor_id
from app.finance.services.panel import panel_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get(
    "/tutor/students/{student_id}/payments/panel",
    response_class=HTMLResponse,
)
def student_payments_panel(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Панель платежей ученика; чужой ученик — 404."""
    student = get_owned_student(db, student_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "finance/_panel.html",
        panel_context(db, student, tutor),
    )
