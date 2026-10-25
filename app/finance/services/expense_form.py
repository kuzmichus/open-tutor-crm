"""Разбор и валидация формы расхода.

Сервис не знает про FastAPI: на вход приходит отображение с полями формы,
на выход — очищенные данные и список ошибок (паттерн `payment_form`).

Правила зеркальны платежу (спека tutor-finance, «Внесение расхода»):

- сумма — целое число рублей строго больше нуля: знак выводится из типа
  записи, хранить его в числе нельзя (как `amount` операций счёта);
- дата обязательна: без неё расход некуда поставить в списке операций;
- категория — только из закрытого списка модели (`EXPENSE_CATEGORIES`):
  форма могла быть отправлена устаревшимися данными;
- комментарий необязателен, но ограничен по длине — предел защищает от
  случайной вставки мегабайта текста.

Дата приходит без времени (`input[type=date]`), время подставляет writer
в момент сохранения (тот же принцип, что у платежа, design D15).
"""

from collections.abc import Mapping
from datetime import date

from app.common.services.forms import parse_rubles, text_value
from app.finance.models.expense import EXPENSE_CATEGORIES
from app.finance.services.payment_form import COMMENT_MAX


def _parse_date(raw: str, errors: list[str]) -> date | None:
    """Дата расхода из `input[type=date]` (YYYY-MM-DD)."""
    if not raw:
        errors.append("Укажите дату расхода.")
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append("Дата расхода указана некорректно.")
        return None


def validate_expense_data(data: dict) -> list[str]:
    """Проверки данных расхода без формы (повтор в writer'е).

    Writer вызывается и из тестов, и из будущих путей: правила не должны
    держаться только на разборе HTTP-формы (паттерн `payment_writer`).
    """
    errors: list[str] = []
    amount = data.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        errors.append("Сумма расхода должна быть больше нуля.")
    if data.get("category") not in EXPENSE_CATEGORIES:
        errors.append("Выберите категорию расхода из списка.")
    if data.get("date") is None:
        errors.append("Укажите дату расхода.")
    comment = data.get("comment")
    if comment and len(comment) > COMMENT_MAX:
        errors.append(f"Комментарий не длиннее {COMMENT_MAX} символов.")
    return errors


def parse_expense_form(form: Mapping) -> tuple[dict, list[str]]:
    """Разбирает и проверяет форму расхода.

    Возвращает `(данные, ошибки)`. Пустой комментарий — это `None`.
    """
    errors: list[str] = []
    raw_category = text_value(form, "category")
    data: dict = {
        "amount": parse_rubles(text_value(form, "amount"), "расхода", errors),
        "category": raw_category if raw_category in EXPENSE_CATEGORIES else None,
        "date": _parse_date(text_value(form, "date"), errors),
        "comment": text_value(form, "comment") or None,
    }
    if raw_category and raw_category not in EXPENSE_CATEGORIES:
        errors.append("Выберите категорию расхода из списка.")

    # Те же правила, что у writer'а, — чтобы сообщения не расходились.
    for message in validate_expense_data({**data, "amount": data["amount"] or 0}):
        if message not in errors:
            errors.append(message)
    return data, errors
