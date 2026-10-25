"""Секция операций страницы финансов: контекст партиала `_operations.html`.

Один сборщик на страницу (`index`) и партиал (`/tutor/finance/operations`):
после сохранения платежа или расхода секция перезапрашивает себя целиком —
и табы, и список, и карточка балансов приезжают одним ответом с сервера.

Сервис не знает про FastAPI: на вход — сессия, репетитор, период и вкладка,
на выход — контекст шаблона.
"""

from sqlalchemy.orm import Session

from app.finance.services.balances import student_balances
from app.finance.services.operations_feed import (
    STUB_TABS,
    TAB_KEYS,
    TAB_LABELS,
    operations_feed,
)


def operations_context(db: Session, tutor, *, period: dict, tab: str) -> dict:
    """Контекст `finance/_operations.html`: вкладка, строки, балансы.

    Балансы делятся на должников и переплатчиков здесь, а не фильтрами в
    шаблоне: карточке нужны и списки, и суммы сторон — оба числа считает
    одно место (правило «шаблон не суммирует сам»).
    """
    balances = student_balances(db, tutor.id)
    debtors = [row for row in balances if row.balance < 0]
    overpayers = [row for row in balances if row.balance > 0]
    return {
        "period": period,
        "tab": tab,
        "tab_keys": TAB_KEYS,
        "tab_labels": TAB_LABELS,
        "tab_is_stub": tab in STUB_TABS,
        "operations": (
            []
            if tab in STUB_TABS
            else operations_feed(
                db,
                tutor.id,
                tutor,
                tab=tab,
                start=period["start"],
                end=period["end"],
            )
        ),
        "debtors": debtors,
        "debtors_total": sum(row.balance for row in debtors),
        "overpayers": overpayers,
        "overpayers_total": sum(row.balance for row in overpayers),
    }
