"""Доступ к одной группе: только своя, чужая — как отсутствующая.

Единое правило выборки одной группы: `id` и `tutor_id` проверяются одним
запросом. Чужая группа и несуществующая неразличимы — 404, а не 403:
существование чужой записи не раскрывается (спека group-management).
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.group.models.group import Group


def get_owned_group(db: Session, group_id: str, tutor_id: str) -> Group:
    """Группа этого репетитора либо 404."""
    group = db.scalars(
        select(Group).where(
            Group.id == group_id,
            Group.tutor_id == tutor_id,
        )
    ).one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return group
