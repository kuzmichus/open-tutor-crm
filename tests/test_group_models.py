"""Тесты моделей групп: дефолты, уникальность состава, каскады."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.student.models.student import Student


def test_group_object_defaults():
    """Создание объекта Group: опциональные поля по умолчанию пустые."""
    group = Group(tutor_id="tutor-1", name="Математика 9А")

    assert group.name == "Математика 9А"
    assert group.description is None
    assert group.price_per_lesson is None
    assert group.meeting_url is None
    assert group.notes is None
    assert group.__tablename__ == "groups"


def test_group_is_saved_with_uuid_and_timestamps(tutor_factory):
    """При сохранении группа получает uuid4-id и метки времени."""
    tutor_id = tutor_factory()

    with SessionLocal() as session:
        group = Group(tutor_id=tutor_id, name="Физика")
        session.add(group)
        session.commit()
        group_id = group.id

    assert len(group_id) == 36
    with SessionLocal() as session:
        saved = session.get(Group, group_id)
        assert saved.created_at is not None
        assert saved.updated_at is not None
        assert saved.price_per_lesson is None


def test_group_member_joined_at_defaults_to_now(tutor_factory, student_factory):
    """Дата вступления по умолчанию — момент добавления («сейчас»)."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)
    # SQLite возвращает naive datetime (без зоны) — сравниваем без зоны.
    before = datetime.now(UTC).replace(tzinfo=None)

    with SessionLocal() as session:
        group = Group(tutor_id=tutor_id, name="Химия")
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, student_id=student_id))
        session.commit()
        member_id = session.query(GroupMember).one().id

    with SessionLocal() as session:
        member = session.get(GroupMember, member_id)
        assert member.joined_at is not None
        assert member.joined_at >= before
        assert member.price_override is None


def test_group_member_pair_is_unique(tutor_factory, student_factory):
    """Один ученик не может состоять в группе дважды."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id)

    with SessionLocal() as session:
        group = Group(tutor_id=tutor_id, name="Биология")
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, student_id=student_id))
        session.commit()
        group_id = group.id

    with SessionLocal() as session:
        session.add(GroupMember(group_id=group_id, student_id=student_id))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("Дубликат пары «группа + ученик» должен был вызвать IntegrityError")


def test_deleting_group_cascades_members_but_keeps_students(
    tutor_factory, student_factory
):
    """Удаление группы уносит членство, ученики остаются."""
    tutor_id = tutor_factory()
    student_id = student_factory(tutor_id=tutor_id, first_name="Целый")

    with SessionLocal() as session:
        group = Group(tutor_id=tutor_id, name="Удаляемая")
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, student_id=student_id))
        session.commit()
        group_id = group.id

    with SessionLocal() as session:
        session.delete(session.get(Group, group_id))
        session.commit()

    with SessionLocal() as session:
        assert session.query(GroupMember).count() == 0
        student = session.get(Student, student_id)
        assert student is not None
        assert student.first_name == "Целый"
