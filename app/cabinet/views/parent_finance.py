"""Страница «Финансы» кабинета родителя: вкладки по детям (design D7).

Агрегат по детям поверх сервисов финансов (`finance_overview` не
меняется): баланс, сумма пополнений и история операций каждого
привязанного ученика плюс общий итог. Активная вкладка — параметр
адреса `?child=<id>`, дефолт — первый ребёнок; чужой или несуществующий
ученик — 404 (`get_child`): изоляция по контакту сохраняется. Ограничение
истории активным ребёнком делает шаблон по `active_child` — нового
сервиса нет (design D7).

Данные видны независимо от роли плательщика — плательщик определяет
расчёты, а не видимость (решение владельца). Время операций показывается
в зоне репетитора — того же, что ведёт привязки этого контакта.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import require_contact_id
from app.cabinet.services.child_finance import finance_overview
from app.cabinet.services.children import children, get_child
from app.database import get_db
from app.student.models.contact import Contact
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/parent/finance", response_class=HTMLResponse)
def parent_finance(
    request: Request,
    child: str | None = None,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Вкладка активного ребёнка и общий итог; чужой `child` — 404."""
    contact = db.get(Contact, contact_id)
    kids = children(db, contact_id)
    tutor = db.get(Tutor, contact.tutor_id)

    # Активная вкладка — параметр адреса; дефолт — первый ребёнок в
    # порядке навигации (тот же контракт вкладок, что у «Домашних заданий»).
    active = get_child(db, child, contact_id) if child else (kids[0] if kids else None)

    blocks, total = finance_overview(db, contact_id)
    return templates.TemplateResponse(
        request,
        "cabinet/parent/finance.html",
        {
            "contact": contact,
            "children": kids,
            "tutor": tutor,
            "blocks": blocks,
            "total": total,
            # Шаблон показывает блок активного ребёнка; None — контакта
            # без детей: остаётся только общий итог.
            "active_child": active,
        },
    )
