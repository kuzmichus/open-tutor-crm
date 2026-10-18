"""Выборки учеников: список с поиском, контакты и карточки для шаблонов.

Связи в проекте объявлены только как FK-колонки (без `relationship()`),
поэтому контакты подгружаются одним запросом с `join` и группируются
в Python — это дешевле, чем N+1 запрос на каждую карточку.
"""

from json import dumps

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.student.models.contact import Contact
from app.student.models.student import Student
from app.student.models.student_contact import StudentContact

# Статусы, которые можно передать фильтром. Пустое значение = «не архивные».
FILTERABLE_STATUSES = ("new", "active", "archived")


def _matches_search(student: Student, needle: str) -> bool:
    """Сравнение без учёта регистра, включая кириллицу.

    SQLite `LIKE`/`lower()` работают без учёта регистра только для ASCII,
    поэтому поиск по имени выполняется в Python: карточек у одного
    репетитора немного, а поведение одинаково на любой локали.
    """
    haystack = " ".join(
        part
        for part in (
            student.first_name,
            student.last_name,
            student.phone,
            student.email,
        )
        if part
    )
    return needle in haystack.casefold()


def list_students(
    db: Session,
    tutor_id: str,
    q: str = "",
    status: str = "",
) -> list[Student]:
    """Ученики репетитора с учётом поиска и фильтра по статусу."""
    stmt = select(Student).where(Student.tutor_id == tutor_id)
    if status in FILTERABLE_STATUSES:
        stmt = stmt.where(Student.status == status)
    else:
        stmt = stmt.where(Student.status != "archived")
    stmt = stmt.order_by(Student.first_name, Student.last_name)
    students = list(db.scalars(stmt).all())

    needle = q.strip().casefold()
    if needle:
        students = [student for student in students if _matches_search(student, needle)]
    return students


def contact_links(db: Session, student_ids: list[str]) -> dict[str, list[dict]]:
    """Привязки контактов, сгруппированные по `student_id`."""
    if not student_ids:
        return {}
    rows = db.execute(
        select(StudentContact, Contact)
        .join(Contact, Contact.id == StudentContact.contact_id)
        .where(StudentContact.student_id.in_(student_ids))
        .order_by(StudentContact.created_at)
    ).all()

    grouped: dict[str, list[dict]] = {student_id: [] for student_id in student_ids}
    for link, contact in rows:
        grouped[link.student_id].append({"link": link, "contact": contact})
    return grouped


def contact_options(
    db: Session,
    tutor_id: str,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    """Контакты репетитора для выпадающего списка «Добавить контакт».

    Уже привязанные к открытой форме ученики контакты (`exclude_ids`)
    исключаются — повторный выбор создал бы дубль строк в форме.
    """
    contacts = db.scalars(
        select(Contact)
        .where(Contact.tutor_id == tutor_id)
        .order_by(Contact.full_name)
    ).all()
    excluded = exclude_ids or set()
    return [
        {
            "id": contact.id,
            "full_name": contact.full_name,
            "phone": contact.phone or "",
            "email": contact.email or "",
        }
        for contact in contacts
        if contact.id not in excluded
    ]


def contact_options_json(
    db: Session,
    tutor_id: str,
    exclude_ids: set[str] | None = None,
) -> str:
    """JSON-массив контактов для `data-`атрибута формы (как часовые зоны)."""
    return dumps(
        contact_options(db, tutor_id, exclude_ids),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_cards(db: Session, students: list[Student]) -> list[dict]:
    """Данные карточек: ученик, его контакты и плательщик.

    `payer` — контакт из числа привязанных; `None` означает «платит сам
    ученик» (так же трактуется `payer_contact_id IS NULL`).
    """
    links = contact_links(db, [student.id for student in students])
    cards = []
    for student in students:
        student_links = links.get(student.id, [])
        payer = None
        if student.payer_contact_id:
            payer = next(
                (
                    item["contact"]
                    for item in student_links
                    if item["contact"].id == student.payer_contact_id
                ),
                None,
            )
        cards.append(
            {"student": student, "contacts": student_links, "payer": payer}
        )
    return cards
