"""Доступ к одной отметке недоступности: только своя, чужая — как отсутствующая.

Единое правило выборки: `id` и `tutor_id` проверяются одним `SELECT`.
Чужая отметка и несуществующая неразличимы — 404, а не 403: существование
чужой записи не раскрывается (спека tutor-unavailability, «Изоляция
отметок по репетитору»).

`require_tutor_id` ри-экспортируется из общего доступа, чтобы вьюхи модуля
не зависели от `app.common.access` напрямую (правило AGENTS.md).
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.access import LOGIN_URL, LoginRequired, require_tutor_id
from app.unavailability.models.unavailability import TutorUnavailability

__all__ = [
    "LOGIN_URL",
    "LoginRequired",
    "get_owned_unavailability",
    "require_tutor_id",
]


def get_owned_unavailability(
    db: Session, mark_id: str, tutor_id: str
) -> TutorUnavailability:
    """Отметка этого репетитора либо 404."""
    mark = db.scalars(
        select(TutorUnavailability).where(
            TutorUnavailability.id == mark_id,
            TutorUnavailability.tutor_id == tutor_id,
        )
    ).one_or_none()
    if mark is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return mark
