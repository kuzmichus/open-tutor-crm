"""Данные дашборда главной страницы (`/tutor/`).

Четыре стат-карточки («Уроки сегодня», «Активные ученики», «Доход за
месяц», «Проведено часов») и два списка («Расписание на сегодня»,
«Недавние платежи») собираются в `dashboard_context` одним заходом:
страница — обзор, и её блоки читают одни и те же окна времени.

Границы «сегодня» и «текущего месяца» считаются настенным временем зоны
педагога и переводятся в UTC по отдельности — та же схема, что у
`local_day_bounds` и `local_week_bounds` (design D3 спеки tutor-timezone):
единый сдвиг UTC-значения ошибался бы в ночи перевода часов.

Изоляция повторяет выборку календаря (`app/calendar/services/week.py`):
у `lessons` нет `tutor_id`, владелец выводится из цели — JOIN на ученика
и группу. Сервис не знает про FastAPI: на вход — `Session` и карточка
репетитора, на выход — контекст шаблона.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_day_bounds, to_utc, today_local
from app.finance.models.account_operation import (
    BALANCE_PAYMENT_STATUS,
    AccountOperation,
)
from app.group.models.group import Group
from app.lesson.models.lesson import LESSON_TYPE_LABELS, Lesson
from app.student.models.student import Student
from app.tutor.services.clock import as_utc
from app.tutor.services.dashboard_lesson import TodayLesson
from app.tutor.services.dashboard_payment import RecentPayment

# Сколько платежей показывает блок «Недавние платежи»: страница — обзор,
# полный список живёт в счёте ученика, здесь архиву делать нечего.
PAYMENTS_LIMIT = 5


def _full_name(first_name: str | None, last_name: str | None) -> str:
    """«Иван Иванов» — полное имя для строки дашборда (по референсу)."""
    return " ".join(part for part in (first_name or "", last_name or "") if part)


def _month_window(tutor) -> tuple[datetime, datetime]:
    """Текущий календарный месяц педагога как интервал aware UTC.

    Начало следующего месяца — настенное время (1-е число, 00:00), а не
    «начало месяца + 30 дней»: месяцы разной длины и перевод часов.
    """
    first = today_local(tutor).replace(day=1)
    if first.month == 12:
        nxt = date(first.year + 1, 1, 1)
    else:
        nxt = date(first.year, first.month + 1, 1)
    return (
        to_utc(datetime.combine(first, time.min), tutor),
        to_utc(datetime.combine(nxt, time.min), tutor),
    )


def today_lessons(db: Session, tutor) -> list[TodayLesson]:
    """Уроки сегодняшнего дня педагога, по времени начала.

    Показываются все статусы: расписание — это план дня, проведённый урок
    из него не исчезает. Подпись строки — предмет педагога; предмет не
    задан — подпись типа урока из закрытого списка модели.
    """
    start, end = local_day_bounds(today_local(tutor), tutor)
    stmt = (
        select(Lesson, Student.first_name, Student.last_name, Group.name)
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(
            or_(Student.tutor_id == tutor.id, Group.tutor_id == tutor.id),
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
        .order_by(Lesson.starts_at, Lesson.id)
    )

    rows: list[TodayLesson] = []
    for lesson, first_name, last_name, group_name in db.execute(stmt).all():
        # CHECK XOR гарантирует ровно одну заполненную цель.
        if lesson.group_id:
            name = group_name or ""
        else:
            name = _full_name(first_name, last_name)
        starts_at = as_utc(lesson.starts_at)
        rows.append(
            TodayLesson(
                starts_at=starts_at,
                ends_at=starts_at + timedelta(minutes=lesson.duration_min or 0),
                name=name,
                subtitle=tutor.subject or LESSON_TYPE_LABELS.get(lesson.type, lesson.type),
                status=lesson.status,
            )
        )
    return rows


def active_students_count(db: Session, tutor_id: str) -> int:
    """Сколько учеников репетитора в статусе «Активный».

    `count()` без GROUP BY всегда возвращает ровно одну строку —
    «может прийти None» здесь не бывает.
    """
    return int(
        db.scalar(
            select(func.count())
            .select_from(Student)
            .where(Student.tutor_id == tutor_id, Student.status == "active")
        )
    )


def month_income(db: Session, tutor) -> int:
    """Сумма оплаченных платежей за текущий месяц педагога, рубли.

    В доход входит только `paid`-платёж — тот же критерий, что в балансе
    (`BALANCE_PAYMENT_STATUS`): иначе карточка «Доход за месяц» разошлась
    бы с деньгами, которые реально получены.
    """
    start, end = _month_window(tutor)
    return int(
        db.scalar(
            select(func.coalesce(func.sum(AccountOperation.amount), 0))
            .join(Student, Student.id == AccountOperation.student_id)
            .where(
                Student.tutor_id == tutor.id,
                AccountOperation.kind == "payment",
                AccountOperation.status == BALANCE_PAYMENT_STATUS,
                AccountOperation.occurred_at >= start,
                AccountOperation.occurred_at < end,
            )
        )
    )


def month_hours(db: Session, tutor) -> int:
    """Проведено часов за текущий месяц педагога (целое число).

    Полные 60 минут дают час, остаток меньше получаса не учитывается,
    от получаса округляется вверх (`+30` до деления): репетитор, проведший
    50 минут, видел бы при простом делении «0 часов» — обидная точность
    для обзорной карточки.
    """
    start, end = _month_window(tutor)
    minutes = int(
        db.scalar(
            select(func.coalesce(func.sum(Lesson.duration_min), 0))
            .join(Student, Student.id == Lesson.student_id, isouter=True)
            .join(Group, Group.id == Lesson.group_id, isouter=True)
            .where(
                or_(Student.tutor_id == tutor.id, Group.tutor_id == tutor.id),
                Lesson.status == "completed",
                Lesson.starts_at >= start,
                Lesson.starts_at < end,
            )
        )
    )
    return (minutes + 30) // 60


def recent_payments(db: Session, tutor, *, limit: int = PAYMENTS_LIMIT) -> list[RecentPayment]:
    """Последние оплаченные платежи по всем ученикам, от новых к старым.

    Только `paid`: блок отвечает на вопрос «сколько и от кого пришло»,
    ожидающий платёж деньгами не стал. Сортировка вторичным `created_at`
    держит порядок при одинаковой дате платежей — как в истории счёта.
    """
    stmt = (
        select(AccountOperation, Student.first_name, Student.last_name)
        .join(Student, Student.id == AccountOperation.student_id)
        .where(
            Student.tutor_id == tutor.id,
            AccountOperation.kind == "payment",
            AccountOperation.status == BALANCE_PAYMENT_STATUS,
        )
        .order_by(
            AccountOperation.occurred_at.desc(),
            AccountOperation.created_at.desc(),
        )
        .limit(limit)
    )
    return [
        RecentPayment(
            occurred_at=as_utc(operation.occurred_at),
            student_name=_full_name(first_name, last_name),
            operation=operation,
        )
        for operation, first_name, last_name in db.execute(stmt).all()
    ]


def dashboard_context(db: Session, tutor) -> dict:
    """Контекст шаблона главной страницы, один заход в базу на блок.

    Счётчик «Запланировано» выводится из уже полученного расписания дня,
    а не отдельным запросом: статусы в строках есть, а второй SELECT
    дублировал бы окно «сегодня».
    """
    today = today_lessons(db, tutor)
    return {
        "today_lessons": today,
        "lessons_today_planned": sum(1 for row in today if row.status == "planned"),
        "active_students": active_students_count(db, tutor.id),
        "month_income": month_income(db, tutor),
        "month_hours": month_hours(db, tutor),
        "recent_payments": recent_payments(db, tutor),
    }
