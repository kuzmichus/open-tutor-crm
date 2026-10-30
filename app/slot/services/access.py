"""Доступ к окнам: `get_owned_slot` и ри-экспорт общего доступа.

Окно — корневая сущность репетитора (`tutor_id` — отдельная колонка), поэтому
доступ проверяется одним `SELECT` по `id` и `tutor_id`. Чужое окно и
несуществующее неразличимы: 404, а не 403 — существование чужой записи не
раскрывается (спека slot-management, «Изоляция по репетитору»).

Ри-экспорт `require_tutor_id`/`LoginRequired` — по правилу AGENTS.md:
вьюхи модуля не зависят от `common` напрямую и не тянут чужой домен.
"""

from sqlalchemy.orm import Session

from app.common.access import (
    LOGIN_URL,
    LoginRequired,
    get_owned_entity,
    require_tutor_id,
)
from app.slot.models.slot import Slot

__all__ = ["LOGIN_URL", "LoginRequired", "get_owned_slot", "require_tutor_id"]


def get_owned_slot(db: Session, slot_id: str, tutor_id: str) -> Slot:
    """Окно этого репетитора либо 404."""
    return get_owned_entity(db, Slot, slot_id, tutor_id)
