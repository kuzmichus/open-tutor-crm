"""Доступ к одной отметке недоступности: только своя, чужая — как отсутствующая.

Единое правило выборки: `id` и `tutor_id` проверяются одним `SELECT`.
Чужая отметка и несуществующая неразличимы — 404, а не 403: существование
чужой записи не раскрывается (спека tutor-unavailability, «Изоляция
отметок по репетитору»).

`require_tutor_id` ри-экспортируется из общего доступа, чтобы вьюхи модуля
не зависели от `app.common.access` напрямую (правило AGENTS.md).
"""

from sqlalchemy.orm import Session

from app.common.access import (
    LOGIN_URL,
    LoginRequired,
    get_owned_entity,
    require_tutor_id,
)
from app.unavailability.models.unavailability import TutorUnavailability

__all__ = ["LOGIN_URL", "LoginRequired", "get_owned_unavailability", "require_tutor_id"]


def get_owned_unavailability(
    db: Session, mark_id: str, tutor_id: str
) -> TutorUnavailability:
    """Отметка этого репетитора либо 404."""
    return get_owned_entity(db, TutorUnavailability, mark_id, tutor_id)
