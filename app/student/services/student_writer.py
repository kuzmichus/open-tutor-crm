"""Сохранение карточки ученика вместе с контактами и плательщиком.

Сохранение атомарно: либо применяются все изменения (поля ученика, привязки
контактов, плательщик), либо не применяется ничего. Поэтому проверка
плательщика выполняется после синхронизации контактов, а при ошибке
транзакция откатывается.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.student.models.contact import Contact
from app.student.models.student import Student
from app.student.models.student_contact import StudentContact
from app.student.services.student_form import validate_payer

# Поля, которые форма записывает напрямую в модель ученика.
# `status` здесь нет: пустое значение означает «статус не передан», и тогда
# текущий статус сохраняется (при создании модель подставит `new`).
_STUDENT_FIELDS = (
    "first_name",
    "last_name",
    "phone",
    "email",
    "kind",
    "grade",
    "school",
    "level",
    "notes",
    "timezone",
    "remind_lesson",
    "remind_homework",
    "remind_cancel",
)

_EMPTY_TO_NONE = ("last_name", "phone", "email", "school", "level", "notes", "timezone")


def _apply_student_fields(student: Student, data: dict) -> None:
    """Переносит очищенные поля формы в модель."""
    for field in _STUDENT_FIELDS:
        value = data[field]
        if field in _EMPTY_TO_NONE and value == "":
            value = None
        setattr(student, field, value)
    # Статус меняется только явным выбором репетитора.
    if data.get("status"):
        student.status = data["status"]


def _tutor_contact(db: Session, tutor_id: str, contact_id: str) -> Contact | None:
    """Контакт этого репетитора; чужой контакт недоступен."""
    return db.scalars(
        select(Contact).where(Contact.id == contact_id, Contact.tutor_id == tutor_id)
    ).one_or_none()


def _sync_contacts(
    db: Session,
    student: Student,
    tutor_id: str,
    rows: list[dict],
) -> set[str]:
    """Приводит привязки ученика к списку строк формы.

    Возвращает id контактов, привязанных к ученику после синхронизации —
    это и есть допустимый набор плательщиков.
    """
    existing = {
        link.contact_id: link
        for link in db.scalars(
            select(StudentContact).where(StudentContact.student_id == student.id)
        ).all()
    }

    kept: set[str] = set()
    for row in rows:
        contact = None
        if row["contact_id"]:
            contact = _tutor_contact(db, tutor_id, row["contact_id"])
        if contact is None:
            # Новый контакт либо ссылка на чужой/удалённый — создаём свой.
            contact = Contact(tutor_id=tutor_id, full_name=row["full_name"])
            db.add(contact)
            db.flush()

        contact.full_name = row["full_name"]
        contact.phone = row["phone"] or None
        contact.email = row["email"] or None

        link = existing.get(contact.id)
        if link is None:
            link = StudentContact(student_id=student.id, contact_id=contact.id)
            db.add(link)
        link.relation = row["relation"] or None
        link.remind_lesson = row["remind_lesson"]
        link.remind_homework = row["remind_homework"]
        link.remind_cancel = row["remind_cancel"]
        kept.add(contact.id)

    for contact_id, link in existing.items():
        if contact_id not in kept:
            db.delete(link)

    db.flush()
    return kept


def create_student(
    db: Session,
    tutor_id: str,
    data: dict,
    rows: list[dict],
) -> tuple[Student | None, list[str]]:
    """Создаёт ученика и его контакты; при ошибке ничего не сохраняет."""
    student = Student(tutor_id=tutor_id)
    _apply_student_fields(student, data)
    db.add(student)
    db.flush()

    linked_ids = _sync_contacts(db, student, tutor_id, rows)
    errors = validate_payer(data["payer_contact_id"], linked_ids)
    if errors:
        db.rollback()
        return None, errors

    student.payer_contact_id = data["payer_contact_id"] or None
    db.commit()
    return student, []


def update_student(
    db: Session,
    student: Student,
    tutor_id: str,
    data: dict,
    rows: list[dict],
) -> list[str]:
    """Обновляет карточку целиком; при ошибке откатывает все изменения."""
    _apply_student_fields(student, data)
    db.flush()

    linked_ids = _sync_contacts(db, student, tutor_id, rows)
    errors = validate_payer(data["payer_contact_id"], linked_ids)
    if errors:
        db.rollback()
        return errors

    student.payer_contact_id = data["payer_contact_id"] or None
    db.commit()
    return []
