"""Запись группы: создание, обновление состава, заметки, удаление.

Сохранение атомарно: либо применяются все изменения (поля группы, состав,
даты и цены участников), либо не применяется ничего — при ошибке
транзакция откатывается.

Проверки названия, лимита и дублей повторяются здесь (решение D6):
форма могла быть отправлена криво или устаревшими данными, валидация
только на клиенте — не валидация.
"""

from datetime import UTC, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.group.services.group_form import (
    effective_member_ids,
    validate_group_data,
    validate_member_pool,
)
from app.group.services.members import member_ids as current_member_ids
from app.student.models.student import Student


def _validate_student_ownership(
    db: Session, tutor_id: str, student_ids: list[str]
) -> list[str]:
    """Добавляемые ученики — только свои (чужие и удалённые не принимаются)."""
    unique_ids = list(dict.fromkeys(student_ids))
    if not unique_ids:
        return []
    existing = set(
        db.scalars(
            select(Student.id).where(
                Student.id.in_(unique_ids),
                Student.tutor_id == tutor_id,
            )
        ).all()
    )
    if any(student_id not in existing for student_id in unique_ids):
        return ["В группу можно добавить только своих учеников."]
    return []


def _joined_at(data: dict, member_id: str) -> datetime | None:
    """Дата вступления из формы; None — «применить значение по умолчанию»."""
    joined = data["joined"].get(member_id)
    if joined is None:
        return None
    return datetime.combine(joined, time.min, tzinfo=UTC)


def _new_member(group_id: str, data: dict, member_id: str) -> GroupMember:
    """Новая запись о членстве: дата из формы либо «сейчас» (дефолт модели)."""
    kwargs: dict = {
        "group_id": group_id,
        "student_id": member_id,
        "price_override": data["prices"].get(member_id),
    }
    joined = _joined_at(data, member_id)
    if joined is not None:
        kwargs["joined_at"] = joined
    return GroupMember(**kwargs)


def create_group(
    db: Session, tutor_id: str, data: dict
) -> tuple[Group | None, list[str]]:
    """Создаёт группу и её состав; при ошибке ничего не сохраняет."""
    errors = validate_group_data(data) + validate_member_pool(data)
    member_ids = effective_member_ids(data) if data["membership_submitted"] else []
    errors += _validate_student_ownership(db, tutor_id, member_ids)
    if errors:
        db.rollback()
        return None, errors

    group = Group(
        tutor_id=tutor_id,
        name=data["name"],
        description=data["description"],
        price_per_lesson=data["price"],
        meeting_url=data.get("meeting_url"),
    )
    db.add(group)
    db.flush()

    for member_id in member_ids:
        db.add(_new_member(group.id, data, member_id))

    db.commit()
    return group, []


def update_group(
    db: Session, group: Group, tutor_id: str, data: dict
) -> list[str]:
    """Обновляет группу и состав; при ошибке откатывает все изменения."""
    errors = validate_group_data(data) + validate_member_pool(data)

    final_ids: list[str] = []
    rows: dict[str, GroupMember] = {}
    if data["membership_submitted"]:
        final_ids = effective_member_ids(data)
        rows = {
            member.student_id: member
            for member in db.scalars(
                select(GroupMember).where(GroupMember.group_id == group.id)
            ).all()
        }
        additions = [sid for sid in final_ids if sid not in rows]
        errors += _validate_student_ownership(db, tutor_id, additions)
    if errors:
        db.rollback()
        return errors

    group.name = data["name"]
    group.description = data["description"]
    group.price_per_lesson = data["price"]
    if data.get("meeting_url_submitted"):
        group.meeting_url = data.get("meeting_url")
    # Заметки сохраняются вместе с группой (спека group-management), но
    # POST без поля заметок (только настройки) их не стирает.
    if data.get("notes_submitted"):
        group.notes = data.get("notes")
    db.flush()

    if data["membership_submitted"]:
        final_set = set(final_ids)
        # Исключения: перечисленные в `removed_members` плюс все, кого
        # больше нет в отправленном списке «оставшихся» (D4).
        for student_id, member in rows.items():
            if student_id not in final_set:
                db.delete(member)
        for student_id in final_ids:
            if student_id in rows:
                # Уже состоящий: меняются дата и индивидуальная цена.
                member = rows[student_id]
                joined = data["joined"].get(student_id)
                if joined is not None:
                    member.joined_at = datetime.combine(joined, time.min, tzinfo=UTC)
                member.price_override = data["prices"].get(student_id)
            else:
                db.add(_new_member(group.id, data, student_id))

    db.commit()
    return []


def update_notes(db: Session, group: Group, notes: str) -> None:
    """Сохраняет заметки к группе (пустая строка — заметок нет)."""
    group.notes = notes.strip() or None
    db.commit()


def delete_group(db: Session, group: Group) -> None:
    """Удаляет группу: членство уходит каскадом, ученики не затрагиваются.

    Каскад обеспечивается FK `ON DELETE CASCADE` и включённым
    `PRAGMA foreign_keys=ON` — отдельных удалений записей не нужно.
    """
    db.delete(group)
    db.commit()
