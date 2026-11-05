"""Обзор (`/tutor/stats?tab=overview`): загрузка, KPI, риск потери, прогноз.

Все карточки учеников считаются из одних строк `student_rows.collect_rows`,
поэтому «Активных» и «Потерянных» на обзоре и в таблице вкладки нельзя
разойтись (design D2). Деньги считаются критериями баланса
(`BALANCE_PAYMENT_STATUS`) и «Дохода за месяц» дашборда: только оплаченные
платежи, возвраты вычитаются.

Загрузка (`utilization`) и карта загрузки (`heatmap`) работают с
астрономическими часами: фактические часы — длительность проведённых
уроков, доступные — рабочие дни периода за вычетом отметок недоступности
(см. `hours`, `availability`). Период «Обзора» по умолчанию — 30 дней.

Прогноз считается по запросу (`forecast=1`): обзор открывают чаще, чем он
нужен, а его агрегаты — лишние запросы на каждый показ (design D3).
"""

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import (
    BALANCE_PAYMENT_STATUS,
    AccountOperation,
)
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.stats.services.availability import available_minutes, period_days
from app.stats.services.heatmap import heatmap_context
from app.stats.services.hours import (
    completed_minutes,
    minutes_to_hours,
)
from app.stats.services.preparation import preparation_context
from app.stats.services.utilization import utilization_context
from app.student.models.student import Student

# Горизонт прогноза в днях (референс: «Прогноз на месяц»).
FORECAST_DAYS = 30


def _revenue(
    db: Session,
    tutor_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """Выручка за период: оплаченные платежи минус возвраты, рубли.

    Возвраты вычитаются, потому что выручкой не являются: платёж, вернувшийся
    ученику, не должен завышать ни «Выручку на час», ни средний чек.
    Списания за уроки не участвуют — это не деньги, пришедшие репетитору.
    Без границ (`None`) — выручка за всё время.
    """
    stmt = (
        select(
            AccountOperation.kind,
            AccountOperation.status,
            AccountOperation.amount,
        )
        .join(Student, Student.id == AccountOperation.student_id)
        .where(Student.tutor_id == tutor_id)
    )
    if start is not None:
        stmt = stmt.where(AccountOperation.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(AccountOperation.occurred_at < end)

    total = 0
    for kind, status, amount in db.execute(stmt).all():
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

    `hours` — астрономическая длительность тех же уроков (групповой урок
    считается один раз): «Запланировано занятий» без часов не отвечает,
    сколько времени эта нагрузка займёт.
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
    minutes = 0
    for lesson in lessons:
        minutes += lesson.duration_min or 0
        if lesson.student_id:
            amount += lesson.price or 0
        else:
            amount += member_prices.get(lesson.group_id, 0)
    return {
        "amount": amount,
        "lessons": len(lessons),
        "days": FORECAST_DAYS,
        "minutes": minutes,
        "hours": minutes_to_hours(minutes),
    }


def _declining_rows(rows: list[dict]) -> list[dict]:
    """Ученики с падением нагрузки — от самого сильного падения к слабому.

    «Ушёл» (архив) не попадает: уход уже показан в «Потерянных», и красный
    флаг «нагрузка −100%» там был бы вторым сообщением об одном и том же.
    """
    return sorted(
        (
            row
            for row in rows
            if row["decline"] and row["activity"] != "lost"
        ),
        key=lambda row: (-row["decline_percent"], row["student"].first_name),
    )


def overview_context(
    db: Session,
    tutor,
    *,
    rows: list[dict],
    now,
    forecast: bool,
    start: datetime | None,
    end: datetime | None,
) -> dict:
    """Контекст вкладки «Обзор» из готовых строк `collect_rows` (design D2).

    «Выручка на час» — целые рубли (выручка периода / фактические часы);
    часов нет — `None`, шаблон покажет «—»: ноль выглядел бы как «час стоит
    0 ₽», хотя занятий просто не было. LTV — средняя выручка на ученика за всё
    время (карточка стоит первой в ряду). Retention передаётся парой
    «числитель/знаменатель»: процент считает хелпер отображения.

    Длина периода в сутках считается один раз: её используют и «Загрузка»
    (масштабирование недельной цели), и «Баланс времени» (недельная
    занятость с подготовкой).
    """
    studied = [row for row in rows if row["last_lesson_at"] is not None]
    active_status = sum(
        1 for row in studied if row["student"].status == "active"
    )

    revenue = _revenue(db, tutor.id, start=start, end=end)
    actual_minutes = completed_minutes(db, tutor.id, start=start, end=end)
    hours = minutes_to_hours(actual_minutes)
    revenue_per_hour = round(revenue / hours) if hours > 0 else None
    days = len(period_days(tutor, start=start, end=end))

    # LTV — средняя выручка на ученика за всё время: это «ценность клиента»,
    # поэтому она не сужается до выбранного периода, в отличие от «Выручки
    # на час». Знаменатель — занимавшиеся хотя бы раз: ученик без занятий
    # ещё не принёс выручки и занижал бы среднее.
    ltv_revenue = _revenue(db, tutor.id)
    ltv = ltv_revenue // len(studied) if studied else None

    risk_rows = sorted(
        (row for row in rows if row["activity"] == "risk"),
        key=lambda row: row["last_lesson_at"],
    )
    declining_rows = _declining_rows(rows)

    return {
        "revenue_per_hour": revenue_per_hour,
        "revenue_period": revenue,
        "hours_actual": hours,
        "ltv": ltv,
        "utilization": utilization_context(
            db,
            tutor,
            start=start,
            end=end,
            actual_minutes=actual_minutes,
            available_minutes=available_minutes(
                db, tutor, start=start, end=end
            ),
            days=days,
        ),
        # Внеурочная занятость: подготовка к урокам и проверка ДЗ. База та же,
        # что у «Загрузки», — фактические минуты периода.
        "preparation": preparation_context(
            db, tutor, actual_minutes=actual_minutes, days=days
        ),
        "heatmap": heatmap_context(db, tutor, now=now),
        "retention_active": active_status,
        "retention_total": len(studied),
        "active_count": sum(1 for row in rows if row["activity"] == "active"),
        "lost_count": sum(1 for row in rows if row["activity"] == "lost"),
        # Самые давние «отвалившиеся» — сверху: их терять ближе всего.
        "risk_rows": risk_rows,
        "declining_rows": declining_rows,
        "risk_total": len(risk_rows) + len(declining_rows),
        "forecast": _forecast(db, tutor, now=now) if forecast else None,
    }