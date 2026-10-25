"""Лента операций страницы финансов: платежи, возвраты и расходы.

Общий список — деньги репетитора: что пришло, что вернулось, что потрачено.
Списания за проведённые уроки (`kind='lesson'`) — внутренние движения
баланса ученика, а не деньги репетитора: они остаются в истории карточки
ученика и в ленту не попадают, иначе вкладки «Доходы»/«Расходы» не
складывались бы в «Все операции».

Три источника сливаются в строки-представления: шаблон не знает про
разнородные модели и форматирование — все подписи и суммы приходят
готовыми (правило «шаблон не форматирует бизнес-данные сам»).

Окно `[start, end)` — то же, что у сводки: список и цифры сверху говорят
об одном периоде.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import AccountOperation
from app.finance.models.expense import EXPENSE_CATEGORY_LABELS, Expense
from app.finance.services.expenses import period_expense_rows
from app.finance.services.presentation import (
    MINUS,
    money,
    operation_datetime,
    operation_kind_label,
    payment_status_label,
)
from app.student.models.student import Student
from app.student.services.presentation import student_full_name

# Сколько строк показывает лента: пагинации нет, страница нужна для
# проверки денег, а не для архива (как HISTORY_LIMIT истории ученика).
FEED_LIMIT = 50

# Ключи вкладок ленты; «all» — умолчание страницы.
TAB_KEYS = ("all", "expenses", "income", "analytics", "forecast")

TAB_LABELS = {
    "all": "Все операции",
    "expenses": "Расходы",
    "income": "Доходы",
    "analytics": "Аналитика",
    "forecast": "Прогноз на месяц",
}

# Вкладки-заглушки: присутствуют по референсу, разделы в разработке.
STUB_TABS = ("analytics", "forecast")


def parse_finance_tab(params) -> str:
    """Ключ вкладки из query; мусор — умолчание «Все операции».

    Вкладка передаётся ссылками табов, опечатка не повод ломать страницу
    (тот же принцип, что у `parse_finance_period`).
    """
    key = params.get("tab", "all")
    return key if key in TAB_KEYS else "all"


def _payment_rows(db: Session, tutor_id: str, tutor, *, start, end) -> list[dict]:
    """Строки платежей и возвратов с именами учеников (без N+1).

    Все платежи при любом статусе, включая «Отменено»: как и в списке
    платежей карточки, репетитор должен видеть, что платёж был и что с ним
    стало (спека student-finance, «Список платежей отдельно от истории»).
    """
    conditions = [Student.tutor_id == tutor_id]
    if start is not None:
        conditions.append(AccountOperation.occurred_at >= start)
    if end is not None:
        conditions.append(AccountOperation.occurred_at < end)

    rows = db.execute(
        select(AccountOperation, Student)
        .join(Student, Student.id == AccountOperation.student_id)
        .where(
            *conditions,
            AccountOperation.kind.in_(("payment", "refund")),
        )
        .order_by(
            AccountOperation.occurred_at.desc(),
            AccountOperation.created_at.desc(),
        )
    ).all()

    feed = []
    for operation, student in rows:
        is_payment = operation.kind == "payment"
        is_paid = operation.status == "paid"
        feed.append(
            {
                "title": student_full_name(student),
                "kind_label": operation_kind_label(operation),
                "status": operation.status if is_payment else None,
                "status_label": (
                    payment_status_label(operation.status) if is_payment else ""
                ),
                # Класс бейджа статуса — закрытый список (paid/pending/
                # cancelled), поэтому собирается здесь, а не в шаблоне.
                "status_class": (
                    f"fin-ops__status--{operation.status}" if is_payment else ""
                ),
                "date": operation_datetime(operation.occurred_at, tutor),
                "comment": operation.comment or "",
                "amount": (
                    f"+{money(operation.amount)}"
                    if is_payment
                    else f"{MINUS}{money(operation.amount)}"
                ),
                "amount_class": (
                    # Пришедшие деньги — зелёные, включая «Ожидает»:
                    # сумма подчёркивает направление, статус — бейджем.
                    "fin-ops__amount--green" if is_payment else "fin-ops__amount--red"
                ),
                "icon": "arrow-down-left" if is_payment else "undo-2",
                "direction": "payment" if is_payment else "refund",
                "_at": operation.occurred_at,
                "_created": operation.created_at,
            }
        )
    return feed


def _expense_rows(expenses: list[Expense], tutor) -> list[dict]:
    """Строки расходов: заголовок — категория, сумма с минусом."""
    return [
        {
            "title": EXPENSE_CATEGORY_LABELS.get(row.category, row.category),
            "kind_label": "Расход",
            "status": None,
            "status_label": "",
            "status_class": "",
            "date": operation_datetime(row.spent_at, tutor),
            "comment": row.comment or "",
            "amount": f"{MINUS}{money(row.amount)}",
            "amount_class": "fin-ops__amount--red",
            "icon": "arrow-up-right",
            "direction": "expense",
            "_at": row.spent_at,
            "_created": row.created_at,
        }
        for row in expenses
    ]


def operations_feed(
    db: Session, tutor_id: str, tutor, *, tab: str, start, end
) -> list[dict]:
    """Строки ленты для вкладки: слияние источников, сортировка, лимит.

    Вкладка выбирает источники: «Все операции» — платежи, возвраты и
    расходы; «Доходы» — только платежи и возвраты; «Расходы» — только
    траты. Сортировка общая — от новых к старым, вторичный ключ
    `created_at` держит стабильный порядок операций одной даты.
    """
    rows: list[dict] = []
    if tab in ("all", "income"):
        rows.extend(_payment_rows(db, tutor_id, tutor, start=start, end=end))
    if tab in ("all", "expenses"):
        rows.extend(
            _expense_rows(
                period_expense_rows(db, tutor_id, start=start, end=end), tutor
            )
        )

    rows.sort(key=lambda row: (row["_at"], row["_created"]), reverse=True)
    return rows[:FEED_LIMIT]
