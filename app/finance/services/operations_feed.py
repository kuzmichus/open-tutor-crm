"""Лента операций страницы финансов: платежи, возвраты, расходы и списания.

Общий список — все движения средств за период: деньги репетитора (платежи,
возвраты, расходы) и списания за проведённые уроки (`kind='lesson'`) —
движение баланса ученика. Уроки входят только во вкладку «Все операции» и в
фильтр «Списания за уроки»: вкладки «Доходы»/«Расходы» — деньги репетитора,
и с уроками они не складывались бы в «Все операции».

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
from app.lesson.models.lesson import LESSON_TYPE_LABELS, Lesson
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

# Ключи фильтра ленты по виду операции (query-параметр `kind`); «all» —
# без фильтра. Фильтр есть только у вкладки «Все операции» — остальные
# вкладки сами являются фильтром.
KIND_KEYS = ("all", "income", "refund", "expense", "lesson")

KIND_LABELS = {
    "all": "Все",
    "income": "Приходы",
    "refund": "Возвраты",
    "expense": "Расходы",
    "lesson": "Списания за уроки",
}

# Фильтр `kind` сужает виды операций счёта в запросе платежей; «Расходы» —
# отдельный источник (`expenses`), до запроса он не доходит.
KIND_OPERATION_KINDS = {
    "all": ("payment", "refund", "lesson"),
    "income": ("payment",),
    "refund": ("refund",),
    "lesson": ("lesson",),
    "expense": (),
}


def parse_finance_tab(params) -> str:
    """Ключ вкладки из query; мусор — умолчание «Все операции».

    Вкладка передаётся ссылками табов, опечатка не повод ломать страницу
    (тот же принцип, что у `parse_finance_period`).
    """
    key = params.get("tab", "all")
    return key if key in TAB_KEYS else "all"


def _lesson_comment(lesson: Lesson | None, note: str | None) -> str:
    """Подпись строки урока: тип урока и заметка через разделитель.

    Урока может не быть (списание пережило удаление урока невозможно —
    каскад, но JOIN всё равно LEFT): тогда подпись короче.
    """
    parts = []
    if lesson is not None:
        parts.append(LESSON_TYPE_LABELS.get(lesson.type, lesson.type))
    if note:
        parts.append(note)
    return " · ".join(parts)


def _payment_rows(
    db: Session,
    tutor_id: str,
    tutor,
    *,
    start,
    end,
    kinds: tuple[str, ...],
) -> list[dict]:
    """Строки операций счёта с именами учеников (без N+1).

    Все платежи при любом статусе, включая «Отменено»: как и в списке
    платежей карточки, репетитор должен видеть, что платёж был и что с ним
    стало (спека student-finance, «Список платежей отдельно от истории»).

    Списания за уроки (`kind='lesson'`) — те же строки: заголовок — имя
    ученика, подпись — тип урока и заметка. `Lesson` нужен только для
    подписи типа, поэтому LEFT JOIN по первичному ключу: без урока строка
    остаётся, подпись просто короче.
    """
    conditions = [Student.tutor_id == tutor_id]
    if start is not None:
        conditions.append(AccountOperation.occurred_at >= start)
    if end is not None:
        conditions.append(AccountOperation.occurred_at < end)

    rows = db.execute(
        select(AccountOperation, Student, Lesson)
        .join(Student, Student.id == AccountOperation.student_id)
        .outerjoin(Lesson, Lesson.id == AccountOperation.lesson_id)
        .where(
            *conditions,
            AccountOperation.kind.in_(kinds),
        )
        .order_by(
            AccountOperation.occurred_at.desc(),
            AccountOperation.created_at.desc(),
        )
    ).all()

    feed = []
    for operation, student, lesson in rows:
        is_payment = operation.kind == "payment"
        is_lesson = operation.kind == "lesson"
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
                "comment": (
                    _lesson_comment(lesson, lesson.note if lesson else None)
                    if is_lesson
                    else operation.comment or ""
                ),
                "amount": (
                    f"+{money(operation.amount)}"
                    if is_payment
                    else f"{MINUS}{money(operation.amount)}"
                ),
                "amount_value": operation.amount,
                "amount_class": (
                    # Пришедшие деньги — зелёные, включая «Ожидает»:
                    # сумма подчёркивает направление, статус — бейджем.
                    "fin-ops__amount--green"
                    if is_payment
                    else "fin-ops__amount--red"
                ),
                "icon": (
                    "arrow-down-left" if is_payment else "book-open" if is_lesson else "undo-2"
                ),
                "direction": operation.kind,
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
            "amount_value": row.amount,
            "amount_class": "fin-ops__amount--red",
            "icon": "arrow-up-right",
            "direction": "expense",
            "_at": row.spent_at,
            "_created": row.created_at,
        }
        for row in expenses
    ]


def operations_feed(
    db: Session, tutor_id: str, tutor, *, tab: str, kind: str, start, end
) -> dict:
    """Строки ленты и итоги для вкладки: слияние источников, сортировка, лимит.

    Вкладка выбирает источники: «Все операции» — платежи, возвраты, расходы
    и списания за уроки; «Доходы» — только платежи и возвраты; «Расходы» —
    только траты. Фильтр `kind` применяется только на «Все операциях» —
    остальные вкладки сами являются фильтром. Сортировка общая — от новых
    к старым, вторичный ключ `created_at` держит стабильный порядок
    операций одной даты.

    Итоги считаются по отфильтрованному набору до `FEED_LIMIT` (лимит —
    про размер таблицы, не про арифметику) и только по деньгам репетитора:
    списания за уроки — движение баланса ученика, в итоги они не входят.
    «Приходы» включают платежи всех статусов: итоги — суммы показанных
    строк, а не «учтённых» денег (это семантика сводки).
    """
    rows: list[dict] = []
    if tab in ("all", "income"):
        # Фильтр вида — сужение запроса операций счёта; на «Доходах» вкладка
        # сама задаёт состав (платежи и возвраты), фильтр там не действует.
        op_kinds = KIND_OPERATION_KINDS[kind] if tab == "all" else ("payment", "refund")
        if op_kinds:
            rows.extend(
                _payment_rows(
                    db, tutor_id, tutor, start=start, end=end, kinds=op_kinds
                )
            )
    if tab in ("all", "expenses") and (tab != "all" or kind in ("all", "expense")):
        rows.extend(
            _expense_rows(
                period_expense_rows(db, tutor_id, start=start, end=end), tutor
            )
        )

    rows.sort(key=lambda row: (row["_at"], row["_created"]), reverse=True)

    income = sum(r["amount_value"] for r in rows if r["direction"] == "payment")
    refund = sum(r["amount_value"] for r in rows if r["direction"] == "refund")
    expense = sum(r["amount_value"] for r in rows if r["direction"] == "expense")
    return {
        "rows": rows[:FEED_LIMIT],
        "income": income,
        "refund": refund,
        "expense": expense,
        "net": income - refund - expense,
    }
