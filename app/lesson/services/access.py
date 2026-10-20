"""Доступ к урокам: `get_owned_lesson` и ри-экспорт общего доступа.

Владелец урока выводится из цели (ученик или группа — у каждого есть
`tutor_id`, решение D3), поэтому выборка идёт через JOIN по цели.
Чужой урок и несуществующий неразличимы: 404, а не 403 — существование
чужой записи не раскрывается (спека lesson-management, «Изоляция уроков»).
"""

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.access import LOGIN_URL, LoginRequired, require_tutor_id
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student

__all__ = ["LOGIN_URL", "LoginRequired", "get_owned_lesson", "require_tutor_id"]


def get_owned_lesson(db: Session, lesson_id: str, tutor_id: str) -> Lesson:
    """Урок этого репетитора либо 404."""
    stmt = (
        select(Lesson)
        .outerjoin(Student, Lesson.student_id == Student.id)
        .outerjoin(Group, Lesson.group_id == Group.id)
        .where(
            Lesson.id == lesson_id,
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
        )
    )
    lesson = db.scalars(stmt).one_or_none()
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return lesson
