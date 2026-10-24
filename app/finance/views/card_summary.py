"""Сводка счёта на странице карточки ученика — фрагмент для перезапроса.

Страница карточки показывает баланс и последние операции (design D12), но
платёж вносится в модалке поверх неё: после сохранения `payment-saved`
обновляет панель вкладки, а блок на странице остался бы со старым числом.
Поэтому у сводки свой маршрут, и она перезапрашивает себя по тому же
событию — как панель платежей, только разметка короче (правило AGENTS.md:
DOM обновляется с сервера, а не руками в JS).

Ответ — тот же фрагмент `finance/_card_summary.html` с `hx-swap="outerHTML"`:
корень шаблона и есть `<section>`, поэтому подмена не оставляет обёрток.

Чужой ученик и несуществующий неразличимы — 404.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import get_owned_student, require_tutor_id
from app.finance.services.card_summary import card_summary_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get(
    "/tutor/students/{student_id}/finance/summary",
    response_class=HTMLResponse,
)
def student_finance_summary(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Сводка счёта ученика для страницы карточки; чужой ученик — 404."""
    student = get_owned_student(db, student_id, tutor_id)
    return templates.TemplateResponse(
        request,
        "finance/_card_summary.html",
        card_summary_context(db, student, db.get(Tutor, tutor_id)),
    )
