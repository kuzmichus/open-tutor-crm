"""Обзор (`/tutor/stats?tab=overview`): KPI-карточки, риск потери, прогноз.

Все карточки считаются из одних строк `student_rows.collect_rows`, поэтому
«Активных» и «Потерянных» на обзоре и в таблице вкладки нельзя разойтись
(design D2). Деньги считаются критериями баланса (`BALANCE_PAYMENT_STATUS`)
и «Дохода за месяц» дашборда: только оплаченные платежи, возвраты вычитаются.

Прогноз считается по запросу (`forecast=1`): обзор открывают чаще, чем он
нужен, а его агрегаты — лишние запросы на каждый показ (design D3).
"""

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import (
    BALANCE_PAYMENT_STATUS,
    AccountOperation,
)
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student

# Горизонт прогноза в днях (референс: «Прогноз на месяц»).
FORECAST_DAYS = 30


def _revenue(db: Session, tutor_id: str) -> int:
    """Выручка за всё время: оплаченные платежи минус возвраты, рубли.

    Возвраты вычитаются, потому что выручкой не является: платёж, вернувшийся
    ученику, не должен завышать LTV. Списания за уроки не участвуют — это
    не деньги, пришедшие репетитору.
    """
    rows = db.execute(
        select(
            AccountOperation.kind,
            AccountOperation.status,
            AccountOperation.amount,
        )
        .join(Student, Student.id == AccountOperation.student_id)
        .where(Student.tutor_id == tutor_id)
    ).all()
    total = 0
    for kind, status, amount in rows:
        if kind == "payment" and status == BALANCE_PAYMENT_STATUS:
            total += amount
        elif kind == "refund":
            total -= amount
    return total


def _forecast(db: Session, tutor, *, now) -> dict:
    """Ожидаемая выручка запланированных уроков на `FORECAST_DAYS` дней.

    Индивидуальный урок — его цена; групповой — цена каждого участника
    (`price_override` или цена группы). Урок без цены даёт ноль: выдумывать
    «среднюю цену» значило бы показать число, которого не будет в кассе.
    """
    end = now + timedelta(days=FORECAST_DAYS)
    lessons = db.scalars(
        select(Lesson)
        .join(Student, Student.id == Lesson.student_id, isouter=True)
        .join(Group, Group.id == Lesson.group_id, isouter=True)
        .where(
            or_(Student.tutor_id == tutor.id, Group.tutor_id == tutor.id),
            Lesson.status == "planned",
            Lesson.starts_at >= now,
            Lesson.starts_at < end,
        ).order_by(Lesson.starts_at)
    ).all()

    group_ids = {lesson.group_id for lesson in lessons if lesson.group_id}
    member_prices: dict[str, int] = {}
    if group_ids:
        rows = db.execute(
            select(
                GroupMember.group_id,
                GroupMember.price_override,
                Group.price_per_lesson,
            )
            .join(Group, Group.id == GroupMember.group_id)
            .where(GroupMember.group_id.in_(group_ids))
        ).all()
        for group_id, price_override, group_price in rows:
            member_prices[group_id] = member_prices.get(group_id, 0) + (
                price_override if price_override is not None else (group_price or 0)
            )

    amount = 0
    for lesson in lessons:
        if lesson.student_id:
            amount += lesson.price or 0
        else:
            amount += member_prices.get(lesson.group_id, 0)
    return {"amount": amount, "lessons": len(lessons), "days": FORECAST_DAYS}


def overview_context(db: Session, tutor, *, rows, now, forecast: bool) -> dict:
    """Контекст вкладки «Обзор» из готовых строк `collect_rows` (design D2).

    LTV — целые рубли (выручка / занимавшиеся); занимавшихся нет — `None`,
    шаблон покажет «—»: ноль выглядел бы как «каждый принёс 0 ₽», хотя
    учеников просто нет. Retention передаётся парой «числитель/знаменатель»:
    процент считает хелпер отображения, а не сервис.
    """
    studied = [row for row in rows if row["last_lesson_at"] is not None]
    active_status = sum(
        1 for row in studied if row["student"].status == "active"
    )

    revenue = _revenue(db, tutor.id)
    ltv = revenue // len(studied) if studied else None

    context = {
        "ltv": ltv,
        "retention_active": active_status,
        "retention_total": len(studied),
        "active_count": sum(1 for row in rows if row["activity"] == "active"),
        "lost_count": sum(1 for row in rows if row["activity"] == "lost"),
        # Самые давние «отвалившиеся» — сверху: их терять ближе всего.
        "risk_rows": sorted(
            (row for row in rows if row["activity"] == "risk"),
            key=lambda row: row["last_lesson_at"],
        ),
        "forecast": _forecast(db, tutor, now=now) if forecast else None,
    }
    return context
