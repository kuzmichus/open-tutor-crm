"""Сводка страницы финансов: поток за период и балансы на сейчас (design D3).

Три рода чисел, и подписи карточек это подчёркивают:

- **Поток за период** — операции в окне `[start, end)` по `occurred_at`
  («Расходы» — по `spent_at` той же таблицы трат): «Доход» (начисленный
  доход: списания за проведённые уроки, включая неоплаченные), «Возвраты»,
  «Чистый доход», «Расходы», «Заработано (уроки)». Считаются запросами
  `GROUP BY kind` c JOIN по владельцу ученика — N+1 на карточку здесь
  недопустим.
- **Касса за период** — «Получено от учеников» (оплаченные платежи минус
  возвраты): деньги, которые реально пришли на счёт. «Чистая прибыль» и
  «Осталось репетитору» считаются по кассе, а не по начислению: расходы
  платятся живыми деньгами.
- **Состояние на сейчас** — «Долги учеников» и «Переплата»: суммы
  отрицательных и положительных балансов всех учеников. Баланс —
  производная (design D3 student-finance), поэтому считается той же
  формулой `signed_amount` в Python по операциям, сгруппированным по
  ученику: второй копии правила денег не появляется.

Смысл разделения (change finance-hours-idle-revenue): репетитор провёл
урок и начислил 1 200 ₽ — это доход, даже если ученик ещё не заплатил.
Та же тысяча двести одновременно лежит в «Долгах учеников» как дебиторка,
а «Чистая прибыль» остаётся кассовой: в ней этой суммы нет, пока деньги
не пришли. Раньше «Доход» показывал платежи, и при начисленных, но
неоплаченных уроках верхняя карточка обнулялась — это и был баг.

К деньгам добавлено время (`time_metrics`): проведённые часы периода,
средняя стоимость часа, часы подготовки по коэффициенту профиля и реальная
стоимость часа с учётом этой подготовки, свободные часы месяца с ценой
простоя и доходы по типам занятий.

Сервис не знает про FastAPI: на вход — сессия, репетитор и период,
на выход — словарь для `finance/_summary.html`.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import AccountOperation
from app.finance.services.balance import signed_amount
from app.finance.services.expenses import period_expenses
from app.finance.services.npd import npd_context
from app.finance.services.time_metrics import (
    idle_context,
    time_context,
    type_insight,
    type_split,
)
from app.student.models.student import Student


def period_flow(db: Session, tutor_id: str, *, start, end) -> dict[str, int]:
    """Суммы операций за окно по видам: `income`, `refunds`, `earned`.

    В доход входят только оплаченные платежи (`status='paid'`): ожидающие
    и отменённые — это обещания, а не деньги (design D4 student-finance).
    Возвраты и списания входят всегда: статуса у них нет.
    """
    conditions = [Student.tutor_id == tutor_id]
    if start is not None:
        conditions.append(AccountOperation.occurred_at >= start)
    if end is not None:
        conditions.append(AccountOperation.occurred_at < end)

    rows = db.execute(
        select(AccountOperation.kind, AccountOperation.status, func.sum(AccountOperation.amount))
        .join(Student, Student.id == AccountOperation.student_id)
        .where(*conditions)
        .group_by(AccountOperation.kind, AccountOperation.status)
    ).all()

    income = refunds = earned = 0
    for kind, status_value, total in rows:
        if kind == "payment" and status_value == "paid":
            income += total
        elif kind == "refund":
            refunds += total
        elif kind == "lesson":
            earned += total
    return {"income": income, "refunds": refunds, "earned": earned}


def balance_sides(db: Session, tutor_id: str) -> dict[str, int]:
    """Долги и переплаты учеников на текущий момент.

    Один запрос операций с JOIN по владельцу, суммы — в Python той же
    формулой, что показывает баланс карточки: числа здесь и в карточке
    ученика не могут разойтись.
    """
    rows = db.execute(
        select(
            AccountOperation.student_id,
            AccountOperation.kind,
            AccountOperation.status,
            AccountOperation.amount,
        )
        .join(Student, Student.id == AccountOperation.student_id)
        .where(Student.tutor_id == tutor_id)
    ).all()

    per_student: dict[str, int] = {}
    for student_id, kind, status_value, amount in rows:
        per_student[student_id] = (
            per_student.get(student_id, 0) + signed_amount(kind, status_value, amount)
        )

    return {
        "debts": sum(value for value in per_student.values() if value < 0),
        "overpayments": sum(value for value in per_student.values() if value > 0),
    }


def compare_note(received: int, earned: int) -> str:
    """Подсказка блока «Заработано и получено» о разнице сумм (design D4)."""
    if received > earned:
        return (
            "Получено больше заработанного: ученики платят вперёд, "
            "за будущие занятия."
        )
    if received < earned:
        return (
            "Получено меньше заработанного: ученики должны "
            "за прошедшие занятия."
        )
    return "Полученное совпадает с заработанным."


def summary_context(db: Session, tutor, *, start, end) -> dict:
    """Контекст `finance/_summary.html`: суммы, касса, время и сравнение.

    `tutor` — объект карточки, а не id: часы и простой считаются в зоне
    педагога, и второй `SELECT` ради неё здесь не нужен — вызывающие вьюхи
    уже загрузили репетитора для проверки сессии.
    """
    tutor_id = tutor.id
    flow = period_flow(db, tutor_id, start=start, end=end)
    sides = balance_sides(db, tutor_id)
    expenses = period_expenses(db, tutor_id, start=start, end=end)

    # Касса: пришли деньги минус возвраты. Начисленный доход (`earned`) —
    # отдельное число верхней карточки, в кассу он не подмешивается.
    received = flow["income"] - flow["refunds"]
    profit = received - expenses

    time = time_context(db, tutor, earned=flow["earned"], start=start, end=end)
    types = type_split(db, tutor, earned=flow["earned"], start=start, end=end)
    # Цена простоя — реальная ставка из карточки времени, а не средняя:
    # новое окно потребует подготовки, поэтому обещать полную выручку
    # по средней стоимости часа было бы неправдой (замечание ревью).
    idle = idle_context(
        db,
        tutor,
        real_rev=time["real_rev_per_hour"],
        coefficient=time["coefficient"],
    )

    # НПД: при выключенном флаге сервис не делает запросов и возвращает
    # `{"enabled": False}`, налог — ноль. Тогда «Чистая прибыль (после
    # налогов)» равна начисленному доходу минус расходы, а разметка блока
    # налога в шаблон не попадает вовсе.
    npd = npd_context(db, tutor, start=start, end=end)
    tax_total = npd["tax"]["total"] if npd["enabled"] else 0
    net_after_tax = flow["earned"] - expenses - tax_total

    return {
        # «Доход» верхней карточки — начисленный доход за проведённые уроки.
        "income": flow["earned"],
        "refunds": flow["refunds"],
        "expenses": expenses,
        "profit": profit,
        # «= Осталось репетитору» блока сравнения: получено минус расходы.
        # Число совпадает с «Чистой прибылью» — это одно и то же правило
        # денег под двумя подписями (сводка и арифметика блока).
        "left_for_tutor": profit,
        # Отрицательный итог (расходы превысили полученное) красится красным:
        # класс решает сервер, шаблон знак не разбирает.
        "left_is_negative": profit < 0,
        "earned": flow["earned"],
        # «Получено от учеников» блока сравнения — касса, а не начисление.
        "received": received,
        "debts": sides["debts"],
        "overpayments": sides["overpayments"],
        "compare_note": compare_note(received, flow["earned"]),
        "time": time,
        "idle": idle,
        "types": types,
        "type_insight": type_insight(types),
        # НПД: налог, лимит и подсказка. `net_after_tax` — прибыль «на
        # руки» по начислению: доход − расходы − расчётный налог (п. 3 ТЗ).
        "npd": npd,
        "net_after_tax": net_after_tax,
        "net_after_tax_is_negative": net_after_tax < 0,
    }
