"""Отчёт по ученику за месяц: итоги занятий и расчёт (по референсу).

Отчёт — только чтение: он ничего не сохраняет и не меняет счёт, как
счёт за период (`invoice.py`). Все числа считаются из операций счёта и
уроков за окно месяца; выдуманных значений нет.

Границы месяца — настенное время зоны педагога (design D3 спеки
tutor-timezone): начало месяца и начало следующего переводятся в UTC
по отдельности через `local_day_bounds`, иначе занятие ночью 1-го числа
уезжало бы в соседний месяц.

«Отменено» из референса не переносится: в модели урока статуса «отменён»
нет (`LESSON_STATUSES` — только «Запланирован»/«Проведён»), и карточка с
вечным нулём была бы выдуманной метрикой (правило «Блоки будущих
модулей»).

Сервис не знает про FastAPI: на вход — `Session`, ученик, репетитор и
(год, месяц), на выход — контекст модалки.
"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_day_bounds, today_local
from app.finance.models.account_operation import (
    BALANCE_PAYMENT_STATUS,
    AccountOperation,
)
from app.finance.services.balance import balance
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.student.services.list_metrics import last_prices


def parse_month(raw: str | None, tutor) -> date:
    """Первый день месяца из `YYYY-MM`; пустое или мусор — текущий месяц.

    Мусор в query не должен давать 500: модалку открывают по ссылке,
    стрелки навигации шлют `month` явно, а опечатка — не повод ломать
    страницу (тот же подход, что `invoice.parse_period`).
    """
    today = today_local(tutor)
    if raw:
        try:
            year, month = (int(part) for part in raw.split("-", maxsplit=1))
            date(year, month, 1)  # вне 1–12 бросит ValueError
            return date(year, month, 1)
        except ValueError:
            pass
    return today.replace(day=1)


def month_window(month: date, tutor) -> tuple[datetime, datetime]:
    """Окно календарного месяца педагога: [1-е число, 1-е следующего) UTC."""
    if month.month == 12:
        nxt = date(month.year + 1, 1, 1)
    else:
        nxt = date(month.year, month.month + 1, 1)
    start, _ = local_day_bounds(month, tutor)
    end, _ = local_day_bounds(nxt, tutor)
    return start, end


def neighbor_months(month: date) -> tuple[date, date]:
    """Предыдущий и следующий месяц для стрелок навигации."""
    if month.month == 1:
        prev = date(month.year - 1, 12, 1)
    else:
        prev = date(month.year, month.month - 1, 1)
    if month.month == 12:
        nxt = date(month.year + 1, 1, 1)
    else:
        nxt = date(month.year, month.month + 1, 1)
    return prev, nxt


def completed_in_window(
    db: Session, student_id: str, start: datetime, end: datetime
) -> int:
    """Проведено занятий за окно: индивидуальные плюс групповые с участием.

    Тот же состав, что в «Проведено» на карточке (`list_metrics.py`):
    отчёт и карточка не должны расходиться в числе занятий.
    """
    total = 0
    individual = db.scalars(
        select(Lesson.id).where(
            Lesson.student_id == student_id,
            Lesson.status == "completed",
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
    ).all()
    total += len(individual)
    grouped = db.scalars(
        select(Lesson.id)
        .join(GroupMember, GroupMember.group_id == Lesson.group_id)
        .where(
            GroupMember.student_id == student_id,
            Lesson.status == "completed",
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
    ).all()
    total += len(grouped)
    return total


def report_context(
    db: Session,
    student,
    tutor,
    *,
    month: date,
) -> dict:
    """Контекст `_report_modal.html`: карточки-итоги и навигация по месяцам.

    Списания и заработок считаются одним проходом по строкам месяца:
    заработок — те же списания, но только по индивидуальным урокам
    (`lesson.type != 'group'`), подсказка «по индивидуальным занятиям»
    объясняет разницу с «Списано за месяц».
    """
    start, end = month_window(month, tutor)

    charges = db.execute(
        select(AccountOperation.amount, Lesson.type)
        .join(Lesson, Lesson.id == AccountOperation.lesson_id, isouter=True)
        .where(
            AccountOperation.student_id == student.id,
            AccountOperation.kind == "lesson",
            AccountOperation.occurred_at >= start,
            AccountOperation.occurred_at < end,
        )
    ).all()
    charged_total = 0
    earned_total = 0
    for amount, lesson_type in charges:
        charged_total += amount
        # Без урока (строка сирота — не бывает по CASCADE) считаем
        # индивидуальным списанием: тип неизвестен, занижать нельзя.
        if lesson_type != "group":
            earned_total += amount

    paid_amounts = db.scalars(
        select(AccountOperation.amount).where(
            AccountOperation.student_id == student.id,
            AccountOperation.kind == "payment",
            AccountOperation.status == BALANCE_PAYMENT_STATUS,
            AccountOperation.occurred_at >= start,
            AccountOperation.occurred_at < end,
        )
    ).all()

    balance_value = balance(db, student.id)
    price_map = last_prices(db, [student.id])
    price = price_map.get(student.id)
    remaining = (
        balance_value // price
        if balance_value > 0 and price and price > 0
        else None
    )

    prev_month, next_month = neighbor_months(month)
    return {
        "report_student": student,
        "report_month": month,
        "report_month_key": f"{month:%Y-%m}",
        "report_prev_key": f"{prev_month:%Y-%m}",
        "report_next_key": f"{next_month:%Y-%m}",
        "report_completed": completed_in_window(db, student.id, start, end),
        "report_charged_total": charged_total,
        "report_charged_count": len(charges),
        "report_earned_total": earned_total,
        "report_paid_total": sum(paid_amounts),
        "report_paid_count": len(paid_amounts),
        "report_balance": balance_value,
        "report_remaining": remaining,
    }
