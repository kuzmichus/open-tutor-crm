"""Выборки групп: список репетитора и данные карточек списка.

Связи в проекте объявлены только как FK-колонки (без `relationship()`),
поэтому участники подгружаются одним запросом с группировкой — это дешевле,
чем N+1 запрос на каждую карточку.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.group.models.group import Group
from app.group.models.group_member import GroupMember


def list_groups(db: Session, tutor_id: str) -> list[Group]:
    """Группы вошедшего репетитора (никаких чужих), по имени."""
    stmt = (
        select(Group)
        .where(Group.tutor_id == tutor_id)
        .order_by(Group.name, Group.id)
    )
    return list(db.scalars(stmt).all())


def member_counts(db: Session, group_ids: list[str]) -> dict[str, int]:
    """Число участников каждой группы одним запросом (без N+1)."""
    if not group_ids:
        return {}
    rows = db.execute(
        select(GroupMember.group_id, func.count().label("count"))
        .where(GroupMember.group_id.in_(group_ids))
        .group_by(GroupMember.group_id)
    ).all()
    return {group_id: count for group_id, count in rows}


def group_options(db: Session, tutor_id: str) -> list[dict]:
    """Данные карточек списка: группа и её число участников.

    Счётчик считается по записям о членстве (спека group-membership:
    счётчик соответствует реальному числу записей), а не по какому-то
    кэшу на группе.
    """
    groups = list_groups(db, tutor_id)
    counts = member_counts(db, [group.id for group in groups])
    return [
        {"group": group, "member_count": counts.get(group.id, 0)}
        for group in groups
    ]
