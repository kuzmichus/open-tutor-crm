"""Страница кабинета родителя `/parent`: секции по детям и общие пункты.

Требует сессию контакта (`require_contact_id`): без неё запрос прерван
редиректом на `/parent/login` (D4). Навигация (сайдбар) собирается по
привязкам `StudentContact`; дети в архиве показываются наравне с
активными — иначе навигация разошлась бы с «Финансами», где их история
остаётся видимой (D5). Основная страница дублирует секции карточками:
кабинет часто открывают с телефона, где сайдбар свёрнут.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import require_contact_id
from app.cabinet.services.children import children
from app.database import get_db
from app.student.models.contact import Contact
from app.templating import templates

router = APIRouter()


@router.get("/parent", response_class=HTMLResponse)
def parent_index(
    request: Request,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Каркас кабинета: заголовок, секции детей, общие пункты и выход."""
    contact = db.get(Contact, contact_id)
    return templates.TemplateResponse(
        request,
        "cabinet/parent/index.html",
        {
            "contact": contact,
            "children": children(db, contact_id),
        },
    )
