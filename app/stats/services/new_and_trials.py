"""Вкладка «Новые и пробные»: заведения, первая оплата, конверсия из пробного.

«Заведено» — карточки учеников, созданные за период. «Стали активными» — ученики,
у которых за период прошёл **первый** оплаченный платёж: не «платежи за период»,
а именно переход в платных (в том числе ученики, заведённые раньше периода).
«Остался» после пробного — у ученика есть проведённое или запланированное на
будущее обычное занятие после пробного; если занятий нет — оплаченный платёж
после пробного (design D7).

Причины по ученикам считаются двумя массовыми выборками (уроки и платежи по всем
ученикам пробных), не запросом на пробное: пробных может быть несколько десятков.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import (
    BALANCE_PAYMENT_STATUS,
    AccountOperation,
)
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.services.clock import as_utc

# С пробных ниже этого числа процент не показывается: «мало данных» (design D7).
MIN_TRIALS_FOR_RATE = 5


def _first_payments(db: Session, tutor_id: str) -> dict[str, object]:
    """Момент первой оплаты каждого ученика (минимум по оплаченным платежам).

    Минимум ищется в Python, а не `MIN()` в SQL: платежей у ученика единицы,
    а группировка с неагрегированной колонкой в SQLite отдала бы произвольную
    строку группы.
    """
    rows = db.execute(
        select(
            AccountOperation.student_id,
            AccountOperation.occurred_at,
        )
        .join(Student, Student.id == AccountOperation.student_id)
        .where(
            Student.tutor_id == tutor_id,
            AccountOperation.kind == "payment",
            AccountOperation.status == BALANCE_PAYMENT_STATUS,
        )
    ).all()
    moments: dict[str, list] = {}
    for student_id, occurred_at in rows:
        moments.setdefault(student_id, []).append(as_utc(occurred_at))
    return {student_id: min(values) for student_id, values in moments.items()}


def new_students_stats(db: Session, tutor, *, start, end) -> dict:
    """«Заведено»/«Стали активными» за период и разбивка по педагогу.

    «Стали активными» не ограничена учениками периода: первый платёж мог пройти
    у карточки, заведённой раньше. Границы `None` — «Всё время».
    """
    stmt = select(Student).where(Student.tutor_id == tutor.id)
    if start is not None:
        stmt = stmt.where(Student.created_at >= start)
    if end is not None:
        stmt = stmt.where(Student.created_at < end)
    created_students = list(db.scalars(stmt).all())

    first_payments = _first_payments(db, tutor.id)
    activated = 0
    for occurred_at in first_payments.values():
        if start is not None and occurred_at < start:
            continue
        if end is not None and occurred_at >= end:
            continue
        activated += 1

    return {
        "created": len(created_students),
        "activated": activated,
        # Педагог один — владелец аккаунта (design D4); строка разбивки одна.
        "rows": [
            {
                "name": tutor.name,
                "created": len(created_students),
                "activated": activated,
            }
        ],
    }


def trial_conversion(db: Session, tutor, *, start, end, now) -> dict:
    """Проведённые пробные за период: кто остался и по какой причине.

    Возвращаются: строка рейтинга (педагог, пробных, остались), список пробных
    поимённо с причиной (для раскрытия по клику) и число незасчитанных для
    строки сверки. Пробные без ученика в модели невозможны (XOR-цель), но
    групповые пробные не попадают в рейтинг: у них нет «своего» ученика.
    """
    stmt = (
        select(Lesson, Student.first_name, Student.last_name)
        .join(Student, Student.id == Lesson.student_id)
        .where(
            Student.tutor_id == tutor.id,
            Lesson.type == "trial",
            Lesson.status == "completed",
            Lesson.student_id.is_not(None),
        )
        .order_by(Lesson.starts_at.desc())
    )
    if start is not None:
        stmt = stmt.where(Lesson.starts_at >= start)
    if end is not None:
        stmt = stmt.where(Lesson.starts_at < end)
    trials = list(db.execute(stmt).all())

    student_ids = {lesson.student_id for lesson, _f, _l in trials}
    lessons_after: dict[str, list] = {}
    payments_after: dict[str, list] = {}
    if student_ids:
        rows = db.execute(
            select(
                Lesson.student_id,
                Lesson.starts_at,
                Lesson.status,
            ).where(
                Lesson.student_id.in_(student_ids),
                Lesson.type != "trial",
            )
        ).all()
        for student_id, starts_at, status in rows:
            lessons_after.setdefault(student_id, []).append(
                (as_utc(starts_at), status)
            )
        rows = db.execute(
            select(
                AccountOperation.student_id,
                AccountOperation.occurred_at,
            ).where(
                AccountOperation.student_id.in_(student_ids),
                AccountOperation.kind == "payment",
                AccountOperation.status == BALANCE_PAYMENT_STATUS,
            )
        ).all()
        for student_id, occurred_at in rows:
            payments_after.setdefault(student_id, []).append(as_utc(occurred_at))

    items = []
    kept_count = 0
    for lesson, first_name, last_name in trials:
        student_id = lesson.student_id
        trial_at = as_utc(lesson.starts_at)
        name = " ".join(part for part in (first_name, last_name) if part)

        kept = None
        detail = None
        regular = sorted(lessons_after.get(student_id, []))
        for starts_at, status in regular:
            if starts_at <= trial_at:
                continue
            if status == "completed" or starts_at >= now:
                kept = "lesson"
                detail = starts_at
                break
        if kept is None:
            payments = sorted(
                moment for moment in payments_after.get(student_id, [])
                if moment > trial_at
            )
            if payments:
                kept = "payment"
                detail = payments[0]

        if kept is not None:
            kept_count += 1
        items.append(
            {
                "name": name,
                "trial_at": trial_at,
                "reason": kept,
                "detail": detail,
            }
        )

    return {
        "rows": [
            {
                "name": tutor.name,
                "trials": len(items),
                "kept": kept_count,
            }
        ],
        # Ключ «students», а не «items»: у словаря есть метод .items, и Jinja
        # отдал бы в шаблон метод вместо значения по ключу.
        "students": items,
    }
