"""Контекст страниц модуля mailing: сайдбар, имя владельца."""

from fastapi import Request
from sqlalchemy.orm import Session

from app.tutor.models.tutor import Tutor


def page_context(
    db: Session,
    request: Request,
    tutor_id: str,
    **extra,
) -> dict:
    """Общие переменные шаблона: активный пункт, имя и роль пользователя.

    Имя берётся из БД по `tutor_id` из сессии — в шаблон не попадает ничего,
    что пришло из формы или query-параметра.
    """
    tutor = db.get(Tutor, tutor_id)
    context = {
        "active_page": "mailings",
        "user_name": tutor.name if tutor is not None else "",
        "user_role": "Владелец",
    }
    context.update(extra)
    return context
