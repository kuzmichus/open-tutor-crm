"""Контекст диалога расхода (`finance/_expense_dialog.html`).

Диалог открывается кнопкой «Расход» страницы финансов в контейнер
`#modal-expense`. При ошибке валидации присланные значения перекрывают
умолчания (паттерн `income_dialog_context`): ошибка в сумме не должна
затирать введённую категорию и комментарий.

Сервис не знает про FastAPI: на вход — репетитор и значения формы,
на выход — контекст шаблона.
"""

from datetime import date

from app.common.services.tutor_time import today_local
from app.finance.models.expense import (
    DEFAULT_EXPENSE_CATEGORY,
    EXPENSE_CATEGORIES,
    EXPENSE_CATEGORY_LABELS,
)


def empty_expense_form(today: date) -> dict:
    """Пустая форма расхода: сегодняшняя дата и «Прочее».

    `today` — календарная дата в зоне педагога: сервис не знает про
    «сейчас», это знание приходит снаружи (`today_local`).
    """
    return {
        "amount": "",
        "category": DEFAULT_EXPENSE_CATEGORY,
        "date_value": today.strftime("%Y-%m-%d"),
        "comment": "",
    }


def expense_dialog_context(
    tutor,
    *,
    data: dict | None = None,
    errors: list[str] | None = None,
) -> dict:
    """Контекст диалога: значения полей, категории, ошибки.

    `data` — значения, введённые при ошибке (очищенные `parse_expense_form`).
    """
    values = empty_expense_form(today_local(tutor))
    if data is not None:
        values = {
            "amount": str(data.get("amount") or ""),
            "category": data.get("category") or DEFAULT_EXPENSE_CATEGORY,
            "date_value": (
                data["date"].strftime("%Y-%m-%d") if data.get("date") else ""
            ),
            "comment": data.get("comment") or "",
        }

    return {
        "expense_form": values,
        "expense_errors": errors or [],
        "expense_categories": EXPENSE_CATEGORIES,
        "expense_category_labels": EXPENSE_CATEGORY_LABELS,
    }
