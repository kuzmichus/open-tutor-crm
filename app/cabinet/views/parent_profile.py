"""Вкладка «Профиль» кабинета родителя: просмотр данных контакта (D9).

ФИО, телефон, email контакта и идентификатор входа (email `ContactAccess`) —
в режиме просмотра. Изменений нет: редактирование и смена пароля —
последующий change.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.models.contact_access import ContactAccess
from app.cabinet.services.access import require_contact_id
from app.cabinet.services.children import children
from app.database import get_db
from app.student.models.contact import Contact
from app.templating import templates

router = APIRouter()


@router.get("/parent/profile", response_class=HTMLResponse)
def parent_profile(
    request: Request,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Данные контакта и входа; одна вкладка независимо от числа детей."""
    contact = db.get(Contact, contact_id)
    access = db.scalars(
        select(ContactAccess).where(ContactAccess.contact_id == contact_id)
    ).first()
    return templates.TemplateResponse(
        request,
        "cabinet/parent/profile.html",
        {
            "contact": contact,
            "children": children(db, contact_id),
            "access": access,
        },
    )
