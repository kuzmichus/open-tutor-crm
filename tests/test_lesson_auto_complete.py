"""Автозавершение не отмеченных уроков (задание cron, 24 часа после конца).

Сервис тестируется напрямую (у cron нет HTTP-маршрута) тем же путём, что
использует runner: своя сессия `SessionLocal` и коммит. Проверяются деньги
(списание тем же кодом, что при ручной отметке) и границы 24-часового окна.
"""

from datetime import timedelta

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.lesson.models.lesson import Lesson
from app.lesson.services.auto_complete import auto_complete_finished_lessons
from app.student.models.student import Student
from app.tutor.services.clock import utcnow

OVERDUE_START = utcnow() - timedelta(hours=25)


def _run_auto_complete() -> int:
    """Прогон задания так, как его делает runner cron: сессия + коммит."""
    with SessionLocal() as db:
        changed = auto_complete_finished_lessons(db)
        db.commit()
    return changed


def _lesson(lesson_id: str):
    with SessionLocal() as db:
        return db.get(Lesson, lesson_id)


def _charges(student_id: str) -> list[AccountOperation]:
    with SessionLocal() as db:
        return list(
            db.query(AccountOperation)
            .filter_by(student_id=student_id, kind="lesson")
            .all()
        )


def test_completes_overdue_and_charges(tutor_factory, student_factory, lesson_factory):
    """Просроченный урок: «Проведён» + списание с occurred_at начала урока."""
    student_id = student_factory()  # статус по умолчанию «новый»
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=OVERDUE_START,
        duration_min=60,
        price=1200,
    )

    assert _run_auto_complete() == 1

    lesson = _lesson(lesson_id)
    assert lesson.status == "completed"
    charges = _charges(student_id)
    assert len(charges) == 1
    assert charges[0].amount == 1200
    assert charges[0].lesson_id == lesson_id
    # occurred_at — начало урока (design D15 спеки student-finance).
    assert charges[0].occurred_at.replace(tzinfo=None) == OVERDUE_START.replace(tzinfo=None)


def test_first_charge_activates_student(tutor_factory, student_factory, lesson_factory):
    """Автозавершение активирует «нового» ученика, как ручная отметка."""
    student_id = student_factory()
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=OVERDUE_START,
        price=1200,
    )

    _run_auto_complete()

    with SessionLocal() as db:
        assert db.get(Student, student_id).status == "active"


def test_recent_unmarked_untouched(tutor_factory, student_factory, lesson_factory):
    """Урок, закончившийся меньше 24 часов назад, не трогается."""
    student_id = student_factory()
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() - timedelta(hours=23),
        duration_min=60,
        price=1200,
    )

    assert _run_auto_complete() == 0
    assert _lesson(lesson_id).status == "planned"
    assert _charges(student_id) == []


def test_future_lesson_untouched(tutor_factory, student_factory, lesson_factory):
    """Будущий урок задание не затрагивает."""
    student_id = student_factory()
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() + timedelta(days=2),
        price=1200,
    )

    assert _run_auto_complete() == 0
    assert _lesson(lesson_id).status == "planned"


def test_completed_lesson_untouched(tutor_factory, student_factory, lesson_factory):
    """Уже проведённый урок не обрабатывается повторно."""
    student_id = student_factory()
    lesson_factory(
        student_id=student_id,
        status="completed",
        starts_at=OVERDUE_START,
        price=1200,
    )

    assert _run_auto_complete() == 0
    # Фабрика уроков списаний не создаёт (design D6 спеки student-finance):
    # если задание сработало бы, здесь появилось бы лишнее списание.
    assert _charges(student_id) == []


def test_boundary_just_over_24h_is_completed(
    tutor_factory, student_factory, lesson_factory
):
    """Граница окна: конец урока сутки назад — завершается.

    Начало за 24,5 часа с длительностью 30 минут даёт конец ровно сутки
    назад; «сейчас» на запросе всегда чуть позже захваченного момента,
    поэтому `<=` гарантированно срабатывает.
    """
    student_id = student_factory()
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() - timedelta(hours=24, minutes=30),
        duration_min=30,
        price=1200,
    )

    assert _run_auto_complete() == 1
    assert _lesson(lesson_id).status == "completed"


def test_boundary_just_under_24h_is_kept(
    tutor_factory, student_factory, lesson_factory
):
    """Конец урока меньше суток назад — урок ещё ждёт ручной отметки."""
    student_id = student_factory()
    lesson_id = lesson_factory(
        student_id=student_id,
        status="planned",
        # Конец = начало + 60 минут ≈ 23:59 назад — до автозавершения минута.
        starts_at=utcnow() - timedelta(hours=24, minutes=59),
        duration_min=60,
        price=1200,
    )

    assert _run_auto_complete() == 0
    assert _lesson(lesson_id).status == "planned"


def test_group_lesson_charges_members(
    tutor_factory, student_factory, group_factory, group_member_factory, lesson_factory
):
    """Групповой урок: списание каждому участнику по цене группы."""
    tutor_id = tutor_factory()
    first = student_factory(tutor_id=tutor_id)
    second = student_factory(tutor_id=tutor_id)
    group_id = group_factory(tutor_id=tutor_id, price_per_lesson=800)
    group_member_factory(group_id=group_id, student_id=first)
    group_member_factory(group_id=group_id, student_id=second, price_override=500)
    lesson_id = lesson_factory(
        student_id=None,
        group_id=group_id,
        status="planned",
        starts_at=OVERDUE_START,
        price=None,
    )

    assert _run_auto_complete() == 1
    assert _lesson(lesson_id).status == "completed"

    first_charge = _charges(first)
    second_charge = _charges(second)
    assert [charge.amount for charge in first_charge] == [800]
    # Индивидуальная цена участника сильнее общей цены группы.
    assert [charge.amount for charge in second_charge] == [500]
