"""Тесты недельной сетки кабинета родителя (change parent-cabinet-unified-pages).

Сервис `cabinet/services/parent_calendar.py`: уроки всех детей контакта
на одной неделе (индивидуальные и групповые), подпись «Имя · Группа»,
цвет карточки — всегда цвет ребёнка, «★ N» у оценённого прошедшего урока,
«Ближайшее занятие» среди всех детей. Даты — `utcnow() ± timedelta`
(фиксированные даты протухают: уроки уезжают в прошлое).
"""

from datetime import UTC, datetime, time, timedelta

from app.calendar.services.week import week_start
from app.cabinet.services.children import children as contact_children
from app.cabinet.services.parent_calendar import (
    display_zone_owner,
    nearest_lesson,
    parent_calendar_context,
    parent_week_lessons,
)
from app.database import SessionLocal
from app.student.models.student_contact import StudentContact
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow

MONDAY = week_start(utcnow().date())


def _link(student_id: str, contact_id: str) -> None:
    with SessionLocal() as db:
        db.add(StudentContact(student_id=student_id, contact_id=contact_id))
        db.commit()


def _at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    """Момент недели MONDAY: зона тестового репетитора — UTC."""
    return datetime.combine(
        MONDAY + timedelta(days=day_offset), time(hour, minute), tzinfo=UTC
    )


def test_week_lessons_both_children_on_one_week(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Уроки двух детей на одной неделе видны в одной сетке, по времени."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    borya = student_factory(tutor_id=tutor_id, first_name="Боря")
    _link(anya, contact_id)
    _link(borya, contact_id)
    early = lesson_factory(student_id=anya, status="planned", starts_at=_at(1, 10))
    late = lesson_factory(student_id=borya, status="planned", starts_at=_at(1, 12))

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        rows = parent_week_lessons(
            db, contact_children(db, contact_id), MONDAY, tutor
        )

    assert [row.lesson.id for row in rows] == [early, late]
    assert [row.target_name for row in rows] == ["Аня", "Боря"]


def test_week_lessons_excludes_foreign_student(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Урок ученика, не привязанного к контакту, в сетку родителя не попадает."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    own = student_factory(tutor_id=tutor_id, first_name="Аня")
    stranger = student_factory(tutor_id=tutor_id, first_name="Чужой")
    _link(own, contact_id)
    lesson_factory(student_id=own, status="planned", starts_at=_at(2, 10))
    lesson_factory(student_id=stranger, status="planned", starts_at=_at(2, 11))

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        rows = parent_week_lessons(
            db, contact_children(db, contact_id), MONDAY, tutor
        )

    assert [row.target_name for row in rows] == ["Аня"]


def test_group_lesson_label_and_child_color(
    tutor_factory, contact_factory, student_factory, group_factory,
    group_member_factory, lesson_factory,
):
    """Групповой урок: подпись «Имя · Группа», цвет — цвет ребёнка, не группы."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня", color="#3366aa")
    _link(anya, contact_id)
    group_id = group_factory(tutor_id=tutor_id, name="Алгебра-7")
    group_member_factory(group_id=group_id, student_id=anya)
    lesson_factory(
        group_id=group_id, student_id=None, status="planned", starts_at=_at(3, 16)
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        rows = parent_week_lessons(
            db, contact_children(db, contact_id), MONDAY, tutor
        )

    assert [row.target_name for row in rows] == ["Аня · Алгебра-7"]
    # Ось родителя — «который из детей»: цвет группового урока тоже цвет
    # ребёнка, цвет группы в карточку родителя не попадает.
    assert [row.target_color for row in rows] == ["#3366aa"]


def test_individual_lesson_color_is_child_color(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Индивидуальный урок окрашен цветом своего ребёнка."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня", color="#ff8800")
    _link(anya, contact_id)
    lesson_factory(student_id=anya, status="planned", starts_at=_at(0, 9))

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        rows = parent_week_lessons(
            db, contact_children(db, contact_id), MONDAY, tutor
        )

    assert [row.target_color for row in rows] == ["#ff8800"]


def test_context_rating_star_on_completed_lesson(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Оценённый прошедший урок даёт «★ N» в представлении; без оценки — пусто."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)
    graded = lesson_factory(
        student_id=anya, status="completed", starts_at=_at(1, 10)
    )
    with SessionLocal() as db:
        from app.lesson.models.lesson import Lesson

        db.get(Lesson, graded).rating = 5
        db.commit()
    lesson_factory(student_id=anya, status="planned", starts_at=_at(2, 10))

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        context = parent_calendar_context(
            db, contact_children(db, contact_id), tutor, MONDAY
        )

    ratings = {
        event["lesson_id"]: event["rating_label"]
        for day in context["days"]
        for event in day["lessons"]
    }
    assert ratings[graded] == "★ 5"
    planned = [key for key in ratings if key != graded]
    assert all(ratings[key] == "" for key in planned)


def test_nearest_lesson_across_children(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Ближайшее занятие — самое раннее среди всех детей, с именем ребёнка."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    borya = student_factory(tutor_id=tutor_id, first_name="Боря")
    _link(anya, contact_id)
    _link(borya, contact_id)
    # Прошедший урок не кандидат: ближайшее — только будущее.
    lesson_factory(
        student_id=anya, status="planned", starts_at=utcnow() - timedelta(days=1)
    )
    lesson_factory(
        student_id=anya, status="planned", starts_at=utcnow() + timedelta(days=3)
    )
    soon = lesson_factory(
        student_id=borya, status="planned", starts_at=utcnow() + timedelta(days=1)
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        nearest, names = nearest_lesson(
            db, contact_children(db, contact_id), tutor
        )

    assert nearest.id == soon
    assert names == "Боря"


def test_nearest_lesson_group_names_all_children(
    tutor_factory, contact_factory, student_factory, group_factory,
    group_member_factory, lesson_factory,
):
    """Групповое занятие двоих детей: одно ближайшее, имена через запятую."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    borya = student_factory(tutor_id=tutor_id, first_name="Боря")
    _link(anya, contact_id)
    _link(borya, contact_id)
    group_id = group_factory(tutor_id=tutor_id, name="Алгебра-7")
    group_member_factory(group_id=group_id, student_id=anya)
    group_member_factory(group_id=group_id, student_id=borya)
    lesson_factory(
        group_id=group_id,
        student_id=None,
        status="planned",
        starts_at=utcnow() + timedelta(days=1),
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        nearest, names = nearest_lesson(
            db, contact_children(db, contact_id), tutor
        )

    assert nearest is not None
    assert names == "Аня, Боря"


def test_context_without_children_is_empty(tutor_factory, contact_factory):
    """Контакт без детей: сетка пустая, сервис не падает."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        context = parent_calendar_context(
            db, contact_children(db, contact_id), tutor, MONDAY
        )
        nearest, names = nearest_lesson(
            db, contact_children(db, contact_id), tutor
        )

    assert context["is_empty"] is True
    assert nearest is None
    assert names == ""


# --------------------------------------------------------------------------
# Зона отображения: первый ребёнок, фолбэк — педагог (решение владельца)
# --------------------------------------------------------------------------


def test_context_uses_first_child_timezone(
    tutor_factory, contact_factory, student_factory, lesson_factory
):
    """Бейдж и окно недели — в зоне первого ребёнка, не педагога."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    # Порядок навигации — по имени: Аня первая, её пояс и берётся.
    anya = student_factory(
        tutor_id=tutor_id, first_name="Аня", timezone="Europe/Moscow"
    )
    borya = student_factory(
        tutor_id=tutor_id, first_name="Боря", timezone="Asia/Yekaterinburg"
    )
    _link(anya, contact_id)
    _link(borya, contact_id)
    # Воскресенье 23:00 UTC = понедельник 02:00 по Москве: в окне зоны
    # ребёнка урок попадает в колонку понедельника, в окне педагога (UTC)
    # недели он не принадлежал бы вовсе.
    from datetime import UTC, datetime, time, timedelta

    sunday_night_utc = datetime.combine(
        MONDAY - timedelta(days=1), time(23, 0), tzinfo=UTC
    )
    lesson_factory(
        student_id=anya, status="planned", starts_at=sunday_night_utc
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        context = parent_calendar_context(
            db, contact_children(db, contact_id), tutor, MONDAY
        )

    assert context["timezone_label"] == "Europe/Moscow"
    monday_events = [
        event
        for event in context["days"][0]["lessons"]
        if event.get("lesson_id")
    ]
    assert len(monday_events) == 1
    assert monday_events[0]["time_label"].startswith("02:00")


def test_context_falls_back_to_tutor_timezone(
    tutor_factory, contact_factory, student_factory
):
    """У первого ребёнка нет пояса — бейдж показывает зону педагога."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(tutor_id=tutor_id, first_name="Аня")
    _link(anya, contact_id)

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        context = parent_calendar_context(
            db, contact_children(db, contact_id), tutor, MONDAY
        )
        owner = display_zone_owner(
            contact_children(db, contact_id), tutor
        )

    assert context["timezone_label"] == "UTC"
    assert owner is tutor


def test_context_invalid_child_timezone_falls_back_to_tutor(
    tutor_factory, contact_factory, student_factory
):
    """Неизвестное имя пояса у ребёнка — зона педагога, не системная."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(
        tutor_id=tutor_id, first_name="Аня", timezone="Марс/Олимп"
    )
    _link(anya, contact_id)

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        context = parent_calendar_context(
            db, contact_children(db, contact_id), tutor, MONDAY
        )

    assert context["timezone_label"] == "UTC"


def test_display_zone_owner_takes_first_child(
    tutor_factory, contact_factory, student_factory
):
    """Из нескольких детей носитель зоны — именно первый в порядке навигации."""
    tutor_id = tutor_factory(timezone="UTC")
    contact_id = contact_factory(tutor_id=tutor_id)
    anya = student_factory(
        tutor_id=tutor_id, first_name="Аня", timezone="Europe/Moscow"
    )
    borya = student_factory(
        tutor_id=tutor_id, first_name="Боря", timezone="Asia/Yekaterinburg"
    )
    _link(anya, contact_id)
    _link(borya, contact_id)

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        owner = display_zone_owner(contact_children(db, contact_id), tutor)

    assert owner.id == anya
