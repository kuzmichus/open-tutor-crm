"""Разбор формы возврата: сумма и причина (design D5).

Диалог возврата содержит только два поля — сумму и причину: дата возврата
не спрашивается (в требованиях её нет), операция ставится на момент
сохранения (`refunds.create_refund`).

Сервис не знает про FastAPI: на вход — отображение с полями формы, на
выход — очищенные данные и список ошибок. Правило «сумма больше нуля»
здесь то же, что у платежа, а «не больше остатка» и «только по оплаченному
платежу» проверяет `refunds.py` — им нужен платёж и его возвраты.

Причина возврата необязательна, но ограничена по длине: как и у
комментария платежа, предел защищает от случайной вставки мегабайта.
"""

from collections.abc import Mapping

from app.finance.services.payment_form import COMMENT_MAX


def _get(form: Mapping, key: str) -> str:
    """Строковое значение поля формы (отсутствие = пустая строка)."""
    value = form.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _parse_amount(raw: str, errors: list[str]) -> int | None:
    """Сумма возврата: целое число рублей больше нуля.

    Пробелы внутри числа допускаются — «1 000» это та же тысяча (то же
    правило, что у платежа: отказ на пробеле был бы придиркой к
    форматированию, а не проверкой данных).
    """
    if not raw:
        errors.append("Укажите сумму возврата.")
        return None
    cleaned = "".join(raw.split())
    try:
        value = int(cleaned)
    except ValueError:
        errors.append("Сумма возврата — целое число рублей.")
        return None
    if value <= 0:
        errors.append("Сумма возврата должна быть больше нуля.")
        return None
    return value


def validate_refund_data(data: dict) -> list[str]:
    """Проверки данных возврата без формы (повтор в сервисе записи).

    Остаток и статус платежа проверяются отдельно: эти правила требуют
    платёж и его возвраты, поэтому живут в `refunds.validate_refund`.
    """
    errors: list[str] = []
    amount = data.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        errors.append("Сумма возврата должна быть больше нуля.")
    comment = data.get("comment")
    if comment and len(comment) > COMMENT_MAX:
        errors.append(f"Причина возврата не длиннее {COMMENT_MAX} символов.")
    return errors


def parse_refund_form(form: Mapping) -> tuple[dict, list[str]]:
    """Разбирает форму возврата; пустая причина — это `None`."""
    errors: list[str] = []
    data = {
        "amount": _parse_amount(_get(form, "amount"), errors),
        "comment": _get(form, "comment") or None,
    }
    for message in validate_refund_data({**data, "amount": data["amount"] or 0}):
        if message not in errors:
            errors.append(message)
    return data, errors
