"""Общая вкладка «Финансы» кабинета родителя (design D8).

Агрегат по детям поверх сервисов финансов: баланс, сумма пополнений и
история операций каждого привязанного ученика плюс общий итог. Данные
видны независимо от роли плательщика — плательщик определяет расчёты,
а не видимость (решение владельца).

Время операций показывается в зоне репетитора — того же, что ведёт
привязки этого контакта.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import require_contact_id
from app.cabinet.services.child_finance import finance_overview
from app.cabinet.services.children import children
from app.database import get_db
from app.student.models.contact import Contact
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/parent/finance", response_class=HTMLResponse)
def parent_finance(
    request: Request,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Блоки финансов по детям и общий итог; у контакта без детей — только итог (0)."""
    contact = db.get(Contact, contact_id)
    blocks, total = finance_overview(db, contact_id)
    return templates.TemplateResponse(
        request,
        "cabinet/parent/finance.html",
        {
            "contact": contact,
            "children": children(db, contact_id),
            "tutor": db.get(Tutor, contact.tutor_id),
            "blocks": blocks,
            "total": total,
        },
    )
