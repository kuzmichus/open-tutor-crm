"""Доступ к одной группе: только своя, чужая — как отсутствующая.

Единое правило выборки одной группы: `id` и `tutor_id` проверяются одним
запросом. Чужая группа и несуществующая неразличимы — 404, а не 403:
существование чужой записи не раскрывается (спека group-management).
"""

from sqlalchemy.orm import Session

from app.common.access import get_owned_entity
from app.group.models.group import Group


def get_owned_group(db: Session, group_id: str, tutor_id: str) -> Group:
    """Группа этого репетитора либо 404.

    Единое правило выборки одной группы: `id` и `tutor_id` проверяются
    одним запросом. Чужая группа и несуществующая неразличимы — 404, а не
    403: существование чужой записи не раскрывается (спека group-management).
    """
    return get_owned_entity(db, Group, group_id, tutor_id)
