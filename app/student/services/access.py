"""Доступ к страницам учеников: ри-экспорт общего доступа и скоуп по `tutor_id`.

`require_tutor_id` и `LoginRequired` переехали в `app/common/access.py`
(общий код) и здесь ри-экспортируются, чтобы не менять импорты во всех
вьюхах модуля. Вьюхи получают `tutor_id` только отсюда — никогда из формы
или query-параметра.
"""

from sqlalchemy.orm import Session

from app.common.access import (
    LOGIN_URL,
    LoginRequired,
    get_owned_entity,
    require_tutor_id,
)
from app.student.models.contact import Contact
from app.student.models.student import Student

__all__ = [
    "LOGIN_URL",
    "LoginRequired",
    "get_owned_contact",
    "get_owned_student",
    "require_tutor_id",
]


def get_owned_student(db: Session, student_id: str, tutor_id: str) -> Student:
    """Ученик этого репетитора либо 404.

    Единое правило выборки одного ученика: `id` и `tutor_id` проверяются
    одним запросом. Чужой ученик и несуществующий неразличимы — 404, а не
    403 и не пустая страница: существование чужой записи не раскрывается.
    """
    return get_owned_entity(db, Student, student_id, tutor_id)


def get_owned_contact(db: Session, contact_id: str, tutor_id: str) -> Contact:
    """Контакт этого репетитора либо 404.

    Тот же паттерн, что у `get_owned_student`: у `Contact` своя колонка
    `tutor_id`, поэтому выборка делегирует общему `get_owned_entity`.
    Нужно действиям над контактом вне формы ученика — сейчас это бейдж
    «Личный кабинет» на миникарточке (D3 change'а parent-cabinet).
    """
    return get_owned_entity(db, Contact, contact_id, tutor_id)
