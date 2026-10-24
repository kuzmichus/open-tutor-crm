"""Пересчёт баланса ученика (POST, design D7/D8).

Ответ — перерисованная панель (`hx-target="#student-finance-panel"`,
`hx-swap="outerHTML"`): после ремонта исчезает баннер и меняется баланс,
и то и другое приходит с сервера. Отдельный JSON или редирект заставил бы
клиент пересчитывать сумму самостоятельно — вторую копию формулы.

Без `HX-Request` (форма без JS) отвечаем 303 на страницу ученика:
пересчёт уже выполнен, повторять его незачем.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import get_owned_student, require_tutor_id
from app.finance.services.panel import panel_context
from app.finance.services.recalculate import recalculate
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.post(
    "/tutor/students/{student_id}/balance/recalculate",
    response_class=HTMLResponse,
)
def recalculate_balance(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Добавляет недостающие списания и возвращает панель."""
    student = get_owned_student(db, student_id, tutor_id)
    recalculate(db, tutor_id, student.id)

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=f"/tutor/students/{student.id}", status_code=303)

    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "finance/_panel.html",
        panel_context(db, student, tutor),
    )
