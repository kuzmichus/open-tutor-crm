"""Состав группы: лимит участников, дубли, список добавляемых учеников.

`MAX_MEMBERS` — единый источник лимита на сервере: клиентская проверка в
`app/static/groups.js` читает его из `data-max-members` шаблона, а валидация
формы и writer проверяют его заново — форма могла быть отправлена криво
или устаревшими данными.
"""

from json import dumps

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.group.models.group_member import GroupMember
from app.student.models.student import Student

# Максимум участников одновременно (спека group-membership).
MAX_MEMBERS = 10

# Статусы учеников, которых вообще можно предложить для группы:
# архивные не предлагаются (спека group-membership).
_ADDABLE_STATUSES = ("new", "active")


def member_count(db: Session, group_id: str) -> int:
    """Число текущих участников группы."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == group_id)
        )
        or 0
    )


def is_full(db: Session, group_id: str) -> bool:
    """True, если лимит участников исчерпан."""
    return member_count(db, group_id) >= MAX_MEMBERS


def member_ids(db: Session, group_id: str) -> list[str]:
    """Id учеников, уже состоящих в группе."""
    return list(
        db.scalars(
            select(GroupMember.student_id).where(GroupMember.group_id == group_id)
        ).all()
    )


def list_members(db: Session, group_id: str) -> list[dict]:
    """Строки состава одной группой выборкой (без N+1): участник + ученик.

    Порядок — по дате вступления, затем по имени: состав в модалке и в
    форме настроек читается как хронология.
    """
    stmt = (
        select(GroupMember, Student)
        .join(Student, Student.id == GroupMember.student_id)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at, Student.first_name, Student.last_name)
    )
    return [{"member": member, "student": student} for member, student in db.execute(stmt)]


def addable_students(
    db: Session,
    tutor_id: str,
    exclude_ids: set[str] | frozenset[str] | list[str] = (),
) -> list[Student]:
    """Ученики, которых можно добавить в группу.

    Только свои (не чужие) и только активные/новые — архивные не
    предлагаются. Уже состоящие в группе исключаются через `exclude_ids`:
    повторный выбор создал бы дубль.
    """
    excluded = set(exclude_ids)
    stmt = (
        select(Student)
        .where(
            Student.tutor_id == tutor_id,
            Student.status.in_(_ADDABLE_STATUSES),
        )
        .order_by(Student.first_name, Student.last_name, Student.id)
    )
    return [student for student in db.scalars(stmt).all() if student.id not in excluded]


def students_by_ids(
    db: Session, tutor_id: str, student_ids: list[str]
) -> dict[str, Student]:
    """Свои ученики по списку id (для повторной отрисовки формы с ошибкой)."""
    if not student_ids:
        return {}
    stmt = select(Student).where(
        Student.id.in_(student_ids),
        Student.tutor_id == tutor_id,
    )
    return {student.id: student for student in db.scalars(stmt).all()}


def student_full_name(student: Student) -> str:
    """Имя и фамилия одной строкой (пустая фамилия не оставляет хвост)."""
    return " ".join(
        part for part in (student.first_name, student.last_name) if part
    )


def form_member_rows(
    db: Session,
    tutor_id: str,
    member_ids: list[str],
    joined: dict | None = None,
    prices: dict | None = None,
) -> list[dict]:
    """Строки состава для формы: id, имя, дата вступления и индивидуальная цена.

    Используется при повторной отрисовке формы после ошибки валидации и
    после создания ученика из мини-формы (D9): введённый состав не должен
    теряться. Пустая дата и пустая цена — пустые строки полей формы
    (дата по умолчанию — «сейчас», цена — «по общей цене группы»).
    """
    students = students_by_ids(db, tutor_id, member_ids)
    rows: list[dict] = []
    for student_id in member_ids:
        student = students.get(student_id)
        if student is None:
            continue
        joined_at = (joined or {}).get(student_id)
        price = (prices or {}).get(student_id)
        rows.append(
            {
                "id": student.id,
                "name": student_full_name(student),
                "grade": student.grade,
                "joined": joined_at.isoformat() if joined_at else "",
                "price": "" if price is None else str(price),
            }
        )
    return rows


def student_option(student: Student) -> dict:
    """Вариант выбора участника: id, имя и класс (для `data-options`)."""
    return {
        "id": student.id,
        "name": student_full_name(student),
        "grade": student.grade,
    }


def addable_options_json(
    db: Session,
    tutor_id: str,
    exclude_ids: set[str] | frozenset[str] | list[str] = (),
) -> str:
    """JSON-вариантов выбора для `data-`атрибута формы группы."""
    students = addable_students(db, tutor_id, exclude_ids)
    return dumps(
        [student_option(student) for student in students],
        ensure_ascii=False,
        separators=(",", ":"),
    )
