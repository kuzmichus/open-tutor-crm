"""Сервисы модуля group: выборки групп, состав, форма и запись (2.1–2.5)."""

from app.database import SessionLocal
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.group.services.group_form import parse_group_form
from app.group.services.group_writer import (
    create_group,
    delete_group,
    update_group,
    update_notes,
)
from app.group.services.groups import group_options, list_groups, member_counts
from app.group.services.members import (
    MAX_MEMBERS,
    addable_options_json,
    addable_students,
    is_full,
    list_members,
    member_count,
)
from app.student.models.student import Student


# --------------------------------------------------------------------------
# Выборки групп (2.1)
# --------------------------------------------------------------------------


def test_list_groups_returns_only_own_tutor(tutor_factory, group_factory):
    """В списке — только группы вошедшего репетитора."""
    owner = tutor_factory(email="groups-owner@example.com")
    foreign = tutor_factory(email="groups-foreign@example.com")
    group_factory(tutor_id=owner, name="Своя")
    group_factory(tutor_id=foreign, name="Чужая")

    with SessionLocal() as db:
        groups = list_groups(db, owner)

    assert [group.name for group in groups] == ["Своя"]


def test_list_groups_orders_by_name(tutor_factory, group_factory):
    owner = tutor_factory(email="groups-order@example.com")
    group_factory(tutor_id=owner, name="Биология")
    group_factory(tutor_id=owner, name="Алгебра")

    with SessionLocal() as db:
        assert [g.name for g in list_groups(db, owner)] == ["Алгебра", "Биология"]


def test_member_counts_counts_membership_rows(
    tutor_factory, group_factory, student_factory, group_member_factory
):
    """Счётчик участников — число записей о членстве одним запросом."""
    owner = tutor_factory(email="counts@example.com")
    group_id = group_factory(tutor_id=owner)
    other_id = group_factory(tutor_id=owner)
    first = student_factory(tutor_id=owner, first_name="Первый")
    second = student_factory(tutor_id=owner, first_name="Второй")
    group_member_factory(group_id=group_id, student_id=first)
    group_member_factory(group_id=group_id, student_id=second)
    group_member_factory(group_id=other_id, student_id=first)

    with SessionLocal() as db:
        counts = member_counts(db, [group_id, other_id])
        assert counts[group_id] == 2
        assert counts[other_id] == 1
        # Пустой список — пустой результат, без лишнего запроса.
        assert member_counts(db, []) == {}


def test_group_options_builds_cards_with_counts(
    tutor_factory, group_factory, group_member_factory
):
    """Карточки списка несут группу и её число участников."""
    owner = tutor_factory(email="cards@example.com")
    group_id = group_factory(tutor_id=owner, name="Математика 9А", price_per_lesson=1200)
    group_member_factory(group_id=group_id)
    group_member_factory(group_id=group_id)

    with SessionLocal() as db:
        options = group_options(db, owner)

    assert len(options) == 1
    option = options[0]
    assert option["group"].name == "Математика 9А"
    assert option["group"].price_per_lesson == 1200
    assert option["member_count"] == 2


def test_group_options_counts_zero_for_empty_group(
    tutor_factory, group_factory
):
    owner = tutor_factory(email="empty-card@example.com")
    group_factory(tutor_id=owner)

    with SessionLocal() as db:
        [option] = group_options(db, owner)
    assert option["member_count"] == 0


# --------------------------------------------------------------------------
# Состав: лимит, дубли, добавляемые ученики (2.2)
# --------------------------------------------------------------------------


def test_max_members_is_ten():
    """Лимит участников — 10 (спека group-membership)."""
    assert MAX_MEMBERS == 10


def test_member_count_and_full_flag(
    tutor_factory, group_factory, group_member_factory, student_factory
):
    owner = tutor_factory(email="limit@example.com")
    group_id = group_factory(tutor_id=owner)

    with SessionLocal() as db:
        assert member_count(db, group_id) == 0
        assert not is_full(db, group_id)

    for index in range(MAX_MEMBERS):
        student_id = student_factory(tutor_id=owner, first_name=f"Ученик{index}")
        group_member_factory(group_id=group_id, student_id=student_id)

    with SessionLocal() as db:
        assert member_count(db, group_id) == MAX_MEMBERS
        assert is_full(db, group_id)


def test_list_members_returns_member_with_student(
    tutor_factory, group_factory, student_factory, group_member_factory
):
    owner = tutor_factory(email="rows@example.com")
    student_id = student_factory(tutor_id=owner, first_name="Мария", last_name="Петрова")
    group_id = group_factory(tutor_id=owner)
    member_id = group_member_factory(group_id=group_id, student_id=student_id)

    with SessionLocal() as db:
        [row] = list_members(db, group_id)

    assert row["member"].id == member_id
    assert row["student"].first_name == "Мария"
    assert row["student"].last_name == "Петрова"


def test_addable_students_filters_archived_foreign_and_existing(
    tutor_factory, group_factory, student_factory, group_member_factory
):
    """Предлагаются только активные/новые свои, уже состоящие исключены."""
    owner = tutor_factory(email="addable@example.com")
    foreign_tutor = tutor_factory(email="addable-foreign@example.com")
    group_id = group_factory(tutor_id=owner)

    active = student_factory(tutor_id=owner, first_name="Активный", status="active")
    fresh = student_factory(tutor_id=owner, first_name="Новый", status="new")
    archived = student_factory(tutor_id=owner, first_name="Архивный", status="archived")
    existing = student_factory(tutor_id=owner, first_name="УжеВГруппе")
    foreign = student_factory(tutor_id=foreign_tutor, first_name="Чужой")
    group_member_factory(group_id=group_id, student_id=existing)

    with SessionLocal() as db:
        names = [s.first_name for s in addable_students(db, owner, exclude_ids=[existing])]

    assert names == ["Активный", "Новый"]
    assert archived not in names
    assert foreign not in names
    assert existing not in names


def test_addable_options_json_carries_id_name_and_grade(
    tutor_factory, group_factory, student_factory, group_member_factory
):
    """JSON выбора: id, имя (с фамилией) и класс — без архивных и чужих."""
    owner = tutor_factory(email="options@example.com")
    foreign_tutor = tutor_factory(email="options-foreign@example.com")
    group_id = group_factory(tutor_id=owner)
    student_factory(
        tutor_id=owner, first_name="Мария", last_name="Петрова", grade=5
    )
    student_factory(tutor_id=owner, first_name="Архивный", status="archived")
    student_factory(tutor_id=foreign_tutor, first_name="Чужой")
    existing = student_factory(tutor_id=owner, first_name="УжеВГруппе")
    group_member_factory(group_id=group_id, student_id=existing)

    with SessionLocal() as db:
        raw = addable_options_json(db, owner, exclude_ids=[existing])

    assert '"name":"Мария Петрова"' in raw
    assert '"grade":5' in raw
    assert "Архивный" not in raw
    assert "Чужой" not in raw
    assert "УжеВГруппе" not in raw


# --------------------------------------------------------------------------
# Форма группы: разбор и валидация (2.3)
# --------------------------------------------------------------------------


def test_parse_group_form_reads_basic_fields():
    from app.group.services.group_form import parse_group_form

    data, errors = parse_group_form(
        {
            "name": "  Математика 9А  ",
            "description": " Подготовка к ОГЭ ",
            "price": "1 200",
            "members_form": "1",
        }
    )
    assert errors == []
    assert data["name"] == "Математика 9А"
    assert data["description"] == "Подготовка к ОГЭ"
    assert data["price"] == 1200
    assert data["membership_submitted"] is True


def test_parse_group_form_empty_price_is_none():
    from app.group.services.group_form import parse_group_form

    data, errors = parse_group_form({"name": "A", "price": ""})
    assert errors == []
    assert data["price"] is None
    # Пустое описание — это None, а не пустая строка.
    assert data["description"] is None


def test_parse_group_form_requires_name():
    from app.group.services.group_form import parse_group_form

    _, errors = parse_group_form({"name": "   "})
    assert "Укажите название группы." in errors


def test_parse_group_form_rejects_long_name():
    from app.group.services.group_form import parse_group_form

    _, errors = parse_group_form({"name": "x" * 101})
    assert "Название группы не длиннее 100 символов." in errors


def test_parse_group_form_rejects_bad_price():
    from app.group.services.group_form import parse_group_form

    _, errors = parse_group_form({"name": "A", "price": "сто"})
    assert "Цена за урок должна быть целым числом." in errors

    _, errors = parse_group_form({"name": "A", "price": "-5"})
    assert "Цена за урок не может быть отрицательной." in errors


def test_parse_group_form_rejects_member_duplicates():
    from app.group.services.group_form import parse_group_form

    _, errors = parse_group_form(
        {
            "name": "A",
            "members_form": "1",
            "members": ["s1", "s2", "s1"],
        }
    )
    assert "Один и тот же ученик не может состоять в группе дважды." in errors


def test_parse_group_form_rejects_member_limit():
    from app.group.services.group_form import parse_group_form

    ids = [f"s{index}" for index in range(11)]
    _, errors = parse_group_form({"name": "A", "members_form": "1", "members": ids})
    assert "В группе может быть не более 10 участников." in errors


def test_parse_group_form_counts_limit_after_removals():
    """Один «убранный» участник снимает превышение лимита."""
    from app.group.services.group_form import parse_group_form

    ids = [f"s{index}" for index in range(11)]
    _, errors = parse_group_form(
        {
            "name": "A",
            "members_form": "1",
            "members": ids,
            "removed_members": "s10",
        }
    )
    assert not [e for e in errors if "не более" in e]


def test_parse_group_form_without_membership_block_skips_member_checks():
    """POST без блока состава (только название) не трогает и не проверяет состав."""
    from app.group.services.group_form import parse_group_form

    data, errors = parse_group_form({"name": "A", "price": "100"})
    assert errors == []
    assert data["membership_submitted"] is False


def test_parse_group_form_reads_joined_dates_and_prices():
    from app.group.services.group_form import parse_group_form

    data, errors = parse_group_form(
        {
            "name": "A",
            "members_form": "1",
            "members": ["s1"],
            "member_joined_s1": "2026-09-01",
            "member_price_s1": "1000",
            "member_joined_s2": "",
            "member_price_s2": "",
        }
    )
    assert errors == []
    assert data["joined"]["s1"].isoformat() == "2026-09-01"
    assert data["prices"]["s1"] == 1000
    # Пустая индивидуальная цена — None («по общей цене группы»).
    assert data["prices"].get("s2") is None


def test_parse_group_form_rejects_bad_joined_date_and_price():
    from app.group.services.group_form import parse_group_form

    _, errors = parse_group_form(
        {
            "name": "A",
            "members_form": "1",
            "members": ["s1"],
            "member_joined_s1": "вчера",
            "member_price_s1": "тысяча",
        }
    )
    assert "Дата вступления указана некорректно." in errors
    assert "Индивидуальная цена должна быть целым числом." in errors


def test_validate_member_pool_is_reusable_by_writer():
    """Повторная проверка лимита/дублей в writer'е (D6) — те же правила."""
    from app.group.services.group_form import validate_member_pool

    data = {
        "membership_submitted": True,
        "member_ids": [f"s{index}" for index in range(11)],
        "removed_ids": [],
    }
    errors = validate_member_pool(data)
    assert "В группе может быть не более 10 участников." in errors


# --------------------------------------------------------------------------
# Запись группы: полный цикл и защита (2.4)
# --------------------------------------------------------------------------


def _form(**extra):
    """Словарь формы с полями создания по умолчанию."""
    payload = {"name": "Химия", "price": "1200", "description": "9 класс"}
    payload.update(extra)
    return payload


def test_create_group_full_cycle(tutor_factory, student_factory):
    """Создать → добавить участника → изменить цену → удалить."""
    owner = tutor_factory(email="cycle@example.com")
    first = student_factory(tutor_id=owner, first_name="Мария")
    second = student_factory(tutor_id=owner, first_name="Иван")

    # 1. Создание группы с участником и индивидуальной датой вступления.
    data, errors = parse_group_form(
        _form(
            members_form="1",
            members=[first],
            **{f"member_joined_{first}": "2026-09-01"},
        )
    )
    assert errors == []
    with SessionLocal() as db:
        group, save_errors = create_group(db, owner, data)
        assert save_errors == []
        group_id = group.id

    with SessionLocal() as db:
        saved = db.get(Group, group_id)
        assert saved.name == "Химия"
        assert saved.price_per_lesson == 1200
        assert saved.description == "9 класс"
        assert saved.tutor_id == owner
        assert member_count(db, group_id) == 1
        [row] = list_members(db, group_id)
        assert row["student"].id == first
        assert row["member"].joined_at.isoformat()[:10] == "2026-09-01"
        assert row["member"].price_override is None

    # 2. Добавление второго участника с индивидуальной ценой и смена цены группы.
    data, errors = parse_group_form(
        _form(
            price="1500",
            name="Химия 9Б",
            members_form="1",
            members=[first, second],
            **{f"member_price_{second}": "1000"},
        )
    )
    assert errors == []
    with SessionLocal() as db:
        assert update_group(db, db.get(Group, group_id), owner, data) == []

    with SessionLocal() as db:
        saved = db.get(Group, group_id)
        assert saved.name == "Химия 9Б"
        assert saved.price_per_lesson == 1500
        assert member_count(db, group_id) == 2
        rows = {row["student"].id: row for row in list_members(db, group_id)}
        # Дата первого участника не сбрасывается, даже если поле не отправлено.
        assert rows[first]["member"].joined_at.isoformat()[:10] == "2026-09-01"
        assert rows[first]["member"].price_override is None
        assert rows[second]["member"].price_override == 1000

    # 3. Исключение первого участника: запись уходит, ученик цел.
    data, errors = parse_group_form(_form(members_form="1", members=[second]))
    assert errors == []
    with SessionLocal() as db:
        assert update_group(db, db.get(Group, group_id), owner, data) == []

    with SessionLocal() as db:
        assert member_count(db, group_id) == 1
        assert db.get(Student, first) is not None
        rows = list_members(db, group_id)
        assert [row["student"].id for row in rows] == [second]

    # 4. Удаление: группа и членство уходят, ученики остаются.
    with SessionLocal() as db:
        delete_group(db, db.get(Group, group_id))

    with SessionLocal() as db:
        assert db.get(Group, group_id) is None
        assert db.query(GroupMember).filter_by(group_id=group_id).count() == 0
        assert db.get(Student, first) is not None
        assert db.get(Student, second) is not None


def test_create_group_rejects_foreign_student(tutor_factory, student_factory):
    """Чужой ученик не принимается сервером (защита поверх фильтра опций)."""
    owner = tutor_factory(email="foreign-member@example.com")
    foreign_tutor = tutor_factory(email="foreign-member-tutor@example.com")
    foreign_student = student_factory(tutor_id=foreign_tutor, first_name="Чужой")

    data, errors = parse_group_form(
        _form(members_form="1", members=[foreign_student])
    )
    assert errors == []
    with SessionLocal() as db:
        group, save_errors = create_group(db, owner, data)

    assert group is None
    assert "В группу можно добавить только своих учеников." in save_errors
    with SessionLocal() as db:
        assert db.query(Group).filter_by(tutor_id=owner).count() == 0


def test_create_group_rechecks_limit_and_duplicates(tutor_factory):
    """Writer повторяет проверку лимита и дублей (D6), а не доверяет форме."""
    owner = tutor_factory(email="writer-limit@example.com")
    ids = [f"s{index}" for index in range(11)]
    data, _ = parse_group_form(_form(members_form="1", members=ids))
    # parse уже нашёл ошибку — writer обязан отвергнуть такие данные и сам.
    with SessionLocal() as db:
        group, errors = create_group(db, owner, data)
    assert group is None
    assert "В группе может быть не более 10 участников." in errors

    data, _ = parse_group_form(_form(members_form="1", members=["s1", "s1"]))
    with SessionLocal() as db:
        group, errors = create_group(db, owner, data)
    assert group is None
    assert "Один и тот же ученик не может состоять в группе дважды." in errors


def test_update_group_without_membership_block_keeps_members(
    tutor_factory, student_factory
):
    """Переименование без блока состава не трогает участников."""
    owner = tutor_factory(email="rename@example.com")
    student_id = student_factory(tutor_id=owner, first_name="Мария")

    with SessionLocal() as db:
        group = Group(tutor_id=owner, name="Старое имя")
        db.add(group)
        db.flush()
        db.add(GroupMember(group_id=group.id, student_id=student_id))
        db.commit()
        group_id = group.id

    data, errors = parse_group_form({"name": "Новое имя", "price": ""})
    assert errors == []
    with SessionLocal() as db:
        assert update_group(db, db.get(Group, group_id), owner, data) == []

    with SessionLocal() as db:
        saved = db.get(Group, group_id)
        assert saved.name == "Новое имя"
        assert member_count(db, group_id) == 1


def test_update_notes_saves_and_clears(tutor_factory):
    owner = tutor_factory(email="notes@example.com")
    with SessionLocal() as db:
        group = Group(tutor_id=owner, name="Заметочная")
        db.add(group)
        db.commit()
        group_id = group.id

    with SessionLocal() as db:
        update_notes(db, db.get(Group, group_id), "  Ходить по вторникам  ")
    with SessionLocal() as db:
        assert db.get(Group, group_id).notes == "Ходить по вторникам"

    with SessionLocal() as db:
        update_notes(db, db.get(Group, group_id), "   ")
    with SessionLocal() as db:
        assert db.get(Group, group_id).notes is None
