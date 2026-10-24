"""Сводка оплат группы: вкладка «Оплаты» модалки управления (design D2/D4).

Три вопроса, на которые отвечает сводка, — по текущим участникам группы:

- «Списано за занятия группы» — списания `kind='lesson'` по урокам этой
  группы в периоде; списание связано с группой через `lesson_id →
  lessons.group_id`;
- «Возвращено» — возвраты участников в периоде; связать возврат с группой
  точнее схемы нельзя (у возврата только `payment_id`), поэтому объём —
  участники;
- «Долг участников сейчас» — сумма долгов участников; от периода не
  зависит, в подписи — «сейчас».

Итоги складываются из видимых строк: выбывший участник не входит ни в
итог, ни в список, а его исторические списания остаются в его карточке
(design D7 `student-finance`). Иначе при исключённом участнике сумма
строк не сходилась бы с итогом без объяснений.

Сервис не знает про FastAPI: на вход — сессия, группа и репетитор, на
выход — контекст шаблона `finance/_group_panel.html`.
"""

from calendar import monthrange
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_day_bounds, today_local
from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import signed_amount
from app.group.models.group import Group
from app.group.services.members import list_members
from app.lesson.models.lesson import Lesson
from app.student.services.presentation import student_full_name

# Переключатель периода вкладки: закрытый список (AGENTS.md, п. 10).
PERIOD_ALL = "all"
PERIOD_THIS_MONTH = "this_month"
PERIOD_LAST_MONTH = "last_month"
PERIODS = (PERIOD_ALL, PERIOD_THIS_MONTH, PERIOD_LAST_MONTH)
PERIOD_LABELS = {
    PERIOD_ALL: "За всё время",
    PERIOD_THIS_MONTH: "Этот месяц",
    PERIOD_LAST_MONTH: "Прошлый месяц",
}
DEFAULT_PERIOD = PERIOD_ALL


def normalize_period(value: str | None) -> str:
    """Период из query-параметра; неизвестное значение — «За всё время».

    Проверка на сервере, а не в шаблоне: `?period=что-угодно` не должно
    ломать панель, как `?tab=` у карточки ученика.
    """
    return value if value in PERIODS else DEFAULT_PERIOD


def period_bounds(period: str, tutor) -> tuple[datetime | None, datetime | None]:
    """Границы периода в aware UTC: [начало, конец); «За всё время» — (None, None).

    Границы считаются в зоне педагога и переводятся в UTC по отдельности
    (design D3 `tutor-timezone`): занятие вечером 30-го числа попадает в
    «Этот месяц» той зоны, где живёт педагог. «За всё время» — это не
    «от нуля до бесконечности», а отсутствие условия вовсе.
    """
    if period == PERIOD_ALL:
        return None, None

    today = today_local(tutor)
    first = today.replace(day=1)
    if period == PERIOD_LAST_MONTH:
        # Последний день прошлого месяца → его первое число.
        first = (first - timedelta(days=1)).replace(day=1)
    last_day = first.replace(day=monthrange(first.year, first.month)[1])

    start, _ = local_day_bounds(first, tutor)
    _, end = local_day_bounds(last_day, tutor)
    return start, end


def _charges_by_student(
    db: Session,
    group_id: str,
    student_ids: list[str],
    start: datetime | None,
    end: datetime | None,
) -> dict[str, tuple[int, int]]:
    """Списания участников за занятия группы: `{student_id: (сумма, занятий)}`.

    Один запрос с `JOIN lessons` и `GROUP BY student_id` — на отрисовке
    панели N+1 недопустим (правило AGENTS.md). Период фильтруется по
    `occurred_at` самого списания: у списания он равен началу урока
    (design D15 `student-finance`), отдельного join-условия по времени
    не нужно.
    """
    if not student_ids:
        return {}
    stmt = (
        select(
            AccountOperation.student_id,
            func.sum(AccountOperation.amount),
            func.count(),
        )
        .join(Lesson, Lesson.id == AccountOperation.lesson_id)
        .where(
            AccountOperation.kind == "lesson",
            AccountOperation.student_id.in_(student_ids),
            Lesson.group_id == group_id,
        )
        .group_by(AccountOperation.student_id)
    )
    if start is not None:
        stmt = stmt.where(
            AccountOperation.occurred_at >= start,
            AccountOperation.occurred_at < end,
        )
    return {
        student_id: (int(total or 0), int(count))
        for student_id, total, count in db.execute(stmt).all()
    }


def _balances(db: Session, student_ids: list[str]) -> dict[str, int]:
    """Текущий баланс каждого участника одним запросом (может быть отрицательным).

    Операции участников читаются одним `SELECT`, знаки расставляет
    `signed_amount` — та же единственная формула баланса, что и в карточке
    ученика: вторая копия формулы разошлась бы с ней при первом же
    изменении правил.
    """
    if not student_ids:
        return {}
    rows = db.execute(
        select(
            AccountOperation.student_id,
            AccountOperation.kind,
            AccountOperation.status,
            AccountOperation.amount,
        ).where(AccountOperation.student_id.in_(student_ids))
    ).all()
    totals: dict[str, int] = {student_id: 0 for student_id in student_ids}
    for student_id, kind, status, amount in rows:
        totals[student_id] += signed_amount(kind, status, amount)
    return totals


def _refunded_total(
    db: Session,
    student_ids: list[str],
    start: datetime | None,
    end: datetime | None,
) -> int:
    """Сумма возвратов участников в периоде — одним `SUM`."""
    if not student_ids:
        return 0
    stmt = select(func.coalesce(func.sum(AccountOperation.amount), 0)).where(
        AccountOperation.kind == "refund",
        AccountOperation.student_id.in_(student_ids),
    )
    if start is not None:
        stmt = stmt.where(
            AccountOperation.occurred_at >= start,
            AccountOperation.occurred_at < end,
        )
    return int(db.scalar(stmt) or 0)


def group_panel_context(
    db: Session, group: Group, tutor, *, period: str = DEFAULT_PERIOD
) -> dict:
    """Контекст `finance/_group_panel.html`: период, итоги, строки участников.

    Строка участника несёт «Баланс» и «Долг» по всему счёту ученика и
    «Списано» — только за уроки этой группы в периоде (design D2):
    разница объёмов объясняется подписью внизу панели, а не смешением
    правил в одном числе.
    """
    period = normalize_period(period)
    start, end = period_bounds(period, tutor)

    members = list_members(db, group.id)
    student_ids = [row["student"].id for row in members]

    charges = _charges_by_student(db, group.id, student_ids, start, end)
    balances = _balances(db, student_ids)

    member_rows = []
    for row in members:
        student = row["student"]
        charged, lesson_count = charges.get(student.id, (0, 0))
        balance_value = balances.get(student.id, 0)
        member_rows.append(
            {
                "id": student.id,
                "name": student_full_name(student),
                "balance": balance_value,
                "charged": charged,
                "lesson_count": lesson_count,
                # Долг — отрицательный баланс, обрезанный до нуля: «долг
                # −0 ₽» у ученика с положительным балансом был бы ложью.
                "debt": max(0, -balance_value),
            }
        )

    return {
        "group_id": group.id,
        "period": period,
        "period_options": [(key, PERIOD_LABELS[key]) for key in PERIODS],
        "totals": {
            "charged": sum(row["charged"] for row in member_rows),
            "refunded": _refunded_total(db, student_ids, start, end),
            "debt": sum(row["debt"] for row in member_rows),
        },
        "members": member_rows,
    }
