"""Контекст страниц модуля group: активный пункт сайдбара и имя владельца.

Как в модуле student: имя берётся из БД по `tutor_id` из сессии, поэтому
в шаблон не попадает ничего, что пришло из формы или query-параметра.
"""

from sqlalchemy.orm import Session

from app.tutor.models.tutor import Tutor


def page_context(db: Session, tutor_id: str, **extra) -> dict:
    """Общие переменные шаблона групп: активный пункт, имя и роль."""
    tutor = db.get(Tutor, tutor_id)
    context = {
        "active_page": "groups",
        "user_name": tutor.name if tutor is not None else "",
        "user_role": "Владелец",
    }
    context.update(extra)
    return context
