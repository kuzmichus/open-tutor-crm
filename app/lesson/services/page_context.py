"""Контекст страниц модуля lesson: активный пункт сайдбара, имя владельца и зона.

Как в модулях student и group: имя берётся из БД по `tutor_id` из сессии,
поэтому в шаблон не попадает ничего, что пришло из формы или query.
`tutor` (карточка целиком) нужен шаблону для перевода времени уроков в
зону педагога (спека tutor-timezone, «Показ времени идёт в зоне педагога»).
"""

from sqlalchemy.orm import Session

from app.tutor.models.tutor import Tutor


def page_context(db: Session, tutor_id: str, **extra) -> dict:
    """Общие переменные шаблонов уроков: активный пункт, имя, роль и зона."""
    tutor = db.get(Tutor, tutor_id)
    context = {
        "active_page": "lessons",
        "user_name": tutor.name if tutor is not None else "",
        "user_role": "Владелец",
        "tutor": tutor,
    }
    context.update(extra)
    return context
