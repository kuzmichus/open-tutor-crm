"""Доступ к страницам учеников: ри-экспорт общего доступа и скоуп по `tutor_id`.

`require_tutor_id` и `LoginRequired` переехали в `app/common/access.py`
(общий код) и здесь ри-экспортируются, чтобы не менять импорты во всех
вьюхах модуля. Вьюхи получают `tutor_id` только отсюда — никогда из формы
или query-параметра.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.access import LOGIN_URL, LoginRequired, require_tutor_id
from app.student.models.student import Student

__all__ = ["LOGIN_URL", "LoginRequired", "get_owned_student", "require_tutor_id"]


def get_owned_student(db: Session, student_id: str, tutor_id: str) -> Student:
    """Ученик этого репетитора либо 404.

    Единое правило выборки одного ученика: `id` и `tutor_id` проверяются
    одним запросом. Чужой ученик и несуществующий неразличимы — 404, а не
    403 и не пустая страница: существование чужой записи не раскрывается.
    """
    student = db.scalars(
        select(Student).where(
            Student.id == student_id,
            Student.tutor_id == tutor_id,
        )
    ).one_or_none()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return student
