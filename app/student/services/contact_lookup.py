"""Поиск существующего контакта при вводе телефона или email.

Телефон сравнивается по цифрам (формат `+7 555 555-55-55` и
`8 555 555 55 55` — одно и то же), email — без учёта регистра.
Нормализация нужна только для сравнения: хранится отформатированное
значение (см. `app/student/services/phone.py`).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.student.models.contact import Contact
from app.student.models.student_contact import StudentContact
from app.student.services.phone import normalize_phone


def phone_key(value: str | None) -> str:
    """Ключ сравнения телефонов: формат записи не влияет на совпадение.

    Российский номер пишут и как `+7 555 555-55-55`, и как `8 555 555 55 55`.
    Простого удаления нецифровых символов мало: ведущие `7` и `8` дают разные
    строки. Поэтому 11-значный номер с ведущей `8` приводится к `7`, а
    10-значный (без кода страны) получает префикс `7`.
    """
    digits = normalize_phone(value)
    if len(digits) == 11 and digits[0] in {"7", "8"}:
        return "7" + digits[1:]
    if len(digits) == 10:
        return "7" + digits
    return digits


def normalize_email(value: str | None) -> str:
    """Email без пробелов по краям и в нижнем регистре."""
    return (value or "").strip().lower()


def is_linked(db: Session, student_id: str, contact_id: str) -> bool:
    """True, если контакт уже привязан к ученику."""
    if not student_id:
        return False
    return (
        db.scalars(
            select(StudentContact).where(
                StudentContact.student_id == student_id,
                StudentContact.contact_id == contact_id,
            )
        ).first()
        is not None
    )


def find_contact(
    db: Session,
    tutor_id: str,
    phone: str = "",
    email: str = "",
) -> Contact | None:
    """Ищет контакт репетитора по нормализованному телефону или email.

    Чужие контакты не видны: выборка ограничена `tutor_id`, поэтому
    существование контакта другого репетитора не раскрывается.
    """
    phone_key_value = phone_key(phone)
    email_key = normalize_email(email)
    if not phone_key_value and not email_key:
        return None

    candidates = db.scalars(
        select(Contact)
        .where(Contact.tutor_id == tutor_id)
        .order_by(Contact.created_at)
    ).all()

    for contact in candidates:
        if phone_key_value and phone_key(contact.phone) == phone_key_value:
            return contact
        if email_key and normalize_email(contact.email) == email_key:
            return contact
    return None


def lookup_contact(
    db: Session,
    tutor_id: str,
    phone: str = "",
    email: str = "",
    student_id: str = "",
) -> dict | None:
    """Результат ленивого поиска контакта для подсказки в форме.

    `None` — совпадений нет, форма сразу предлагает создать новый контакт.
    Иначе `{"contact": ..., "already_linked": bool}`: уже привязанный
    контакт не предлагается к повторной привязке.
    """
    contact = find_contact(db, tutor_id, phone=phone, email=email)
    if contact is None:
        return None
    return {
        "contact": contact,
        "already_linked": is_linked(db, student_id, contact.id),
    }
