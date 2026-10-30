"""Дети контакта и доступ к страницам ребёнка (design D5).

Секции навигации кабинета собираются по привязкам `StudentContact`:
у контакта — все привязанные ученики, активные и архивные (иначе
навигация разошлась бы с «Финансами», где история архивного ребёнка
остаётся видимой — решение владельца). Страницы ребёнка адресуются id
ученика; доступ — привязка «контакт из сессии ↔ ученик» одним SELECT:
чужой ученик и несуществующий неразличимы — 404.

Отдельная проверка репетитора не нужна: контакт принадлежит ровно одному
репетитору, его привязки — тоже.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.student.models.student import Student
from app.student.models.student_contact import StudentContact


def children(db: Session, contact_id: str) -> list[Student]:
    """Ученики, привязанные к контакту, активные и архивные.

    Порядок по имени: секции навигации стабильны между страницами, у
    ребёнка с одинаковым временем создания не меняется порядок при
    перезагрузке (id — uuid, он «случаен»).
    """
    return list(
        db.scalars(
            select(Student)
            .join(StudentContact, StudentContact.student_id == Student.id)
            .where(StudentContact.contact_id == contact_id)
            .order_by(Student.first_name, Student.last_name, Student.id)
        ).all()
    )


def get_child(db: Session, student_id: str, contact_id: str) -> Student:
    """Ученик, привязанный к контакту из сессии, либо 404.

    Привязка проверяется одним SELECT: `id` ученика и `contact_id` в одном
    запросе через JOIN. Чужой ученик и несуществующий неразличимы — 404,
    а не 403: существование чужой записи не раскрывается.
    """
    student = db.scalars(
        select(Student)
        .join(StudentContact, StudentContact.student_id == Student.id)
        .where(
            Student.id == student_id,
            StudentContact.contact_id == contact_id,
        )
    ).one_or_none()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return student
