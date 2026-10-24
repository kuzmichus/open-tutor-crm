"""Разбор и валидация формы платежа (создание и правка).

Сервис не знает про FastAPI: на вход приходит отображение с полями формы
(`FormData` или обычный dict), на выход — очищенные данные и список ошибок.
Так правила проверяются модульными тестами без поднятия HTTP-клиента.

Правила (спека student-finance, «Внесение платежа»):

- сумма — целое число рублей строго больше нуля: «0 ₽» и отрицательная
  сумма платежом не являются, а хранить знак в сумме нельзя (design D3);
- способ и статус — только из закрытых списков модели (`PAYMENT_METHODS`,
  `PAYMENT_STATUSES`): форма могла быть отправлена устаревшими данными;
- дата обязательна: без неё платёж некуда поставить в истории;
- ученик формой **не** передаётся: он берётся из карточки, из которой
  открыт диалог (design D11) — перенос платежа другому ученику отдельный
  сценарий, которого в требованиях нет.

Дата приходит без времени (`input[type=date]`), а `occurred_at` — одно
сортируемое поле (design D15): время подставляет writer в момент
сохранения, беря текущее локальное время педагога.
"""

from collections.abc import Mapping
from datetime import date

from app.finance.models.account_operation import PAYMENT_METHODS, PAYMENT_STATUSES

# Длина комментария не ограничена моделью (`Text`), но разумный предел
# защищает от случайной вставки мегабайта текста в поле ввода.
COMMENT_MAX = 500


def _get(form: Mapping, key: str) -> str:
    """Строковое значение поля формы (отсутствие = пустая строка)."""
    value = form.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _parse_amount(raw: str, errors: list[str]) -> int | None:
    """Сумма платежа: целое число рублей больше нуля.

    Пробелы (в том числе неразрывные) внутри числа допускаются: «1 200» —
    это та же тысяча двести, что и «1200», и отказ на пробеле был бы
    придиркой к форматированию, а не проверкой данных.
    """
    if not raw:
        errors.append("Укажите сумму платежа.")
        return None
    cleaned = "".join(raw.split())
    try:
        value = int(cleaned)
    except ValueError:
        errors.append("Сумма платежа — целое число рублей.")
        return None
    if value <= 0:
        errors.append("Сумма платежа должна быть больше нуля.")
        return None
    return value


def _parse_date(raw: str, errors: list[str]) -> date | None:
    """Дата платежа из `input[type=date]` (YYYY-MM-DD)."""
    if not raw:
        errors.append("Укажите дату платежа.")
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append("Дата платежа указана некорректно.")
        return None


def _parse_choice(
    raw: str,
    allowed: tuple[str, ...],
    *,
    message: str,
    errors: list[str],
) -> str | None:
    """Значение из закрытого списка; пусто или вне списка — ошибка."""
    if raw not in allowed:
        errors.append(message)
        return None
    return raw


def validate_payment_data(data: dict) -> list[str]:
    """Проверки данных платежа без формы (повтор в writer'е).

    Writer вызывается и из тестов, и из будущих путей: правила не должны
    держаться только на разборе HTTP-формы (паттерн `group_writer`).
    """
    errors: list[str] = []
    amount = data.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        errors.append("Сумма платежа должна быть больше нуля.")
    if data.get("method") not in PAYMENT_METHODS:
        errors.append("Выберите способ оплаты из списка.")
    if data.get("status") not in PAYMENT_STATUSES:
        errors.append("Выберите статус платежа из списка.")
    if data.get("date") is None:
        errors.append("Укажите дату платежа.")
    comment = data.get("comment")
    if comment and len(comment) > COMMENT_MAX:
        errors.append(f"Комментарий не длиннее {COMMENT_MAX} символов.")
    return errors


def parse_payment_form(form: Mapping) -> tuple[dict, list[str]]:
    """Разбирает и проверяет форму платежа.

    Возвращает `(данные, ошибки)`. Данные содержат только значения,
    которые разрешено сохранять: пустой комментарий — это `None`.
    """
    errors: list[str] = []

    data: dict = {
        "amount": _parse_amount(_get(form, "amount"), errors),
        "method": _parse_choice(
            _get(form, "method"),
            PAYMENT_METHODS,
            message="Выберите способ оплаты из списка.",
            errors=errors,
        ),
        "status": _parse_choice(
            _get(form, "status"),
            PAYMENT_STATUSES,
            message="Выберите статус платежа из списка.",
            errors=errors,
        ),
        "date": _parse_date(_get(form, "date"), errors),
        "comment": _get(form, "comment") or None,
    }

    # Проверки, которых не сделал разбор полей (длина комментария):
    # те же правила, что у writer'а, чтобы сообщения не расходились.
    for message in validate_payment_data({**data, "amount": data["amount"] or 0}):
        if message not in errors:
            errors.append(message)

    return data, errors


def payment_to_form(payment, tutor) -> dict:
    """Значения полей диалога из сохранённого платежа.

    Дата берётся из `occurred_at` в зоне педагога: время платежа — момент
    ввода (design D15), поэтому поле показывает тот день, в который платёж
    был внесён. `tutor` нужен для зоны — как в `lesson_form._form_values`.
    """
    from app.common.services.tutor_time import to_local

    return {
        "amount": str(payment.amount),
        "method": payment.method or "",
        "status": payment.status or "",
        "date_value": to_local(payment.occurred_at, tutor).strftime("%Y-%m-%d"),
        "comment": payment.comment or "",
    }


def empty_payment_form(today: date) -> dict:
    """Пустая форма платежа: «Оплачено», «Перевод» и сегодняшняя дата.

    Умолчания выбраны по самому частому случаю — репетитор вносит уже
    полученные деньги. `today` — календарная дата в зоне педагога: сервис
    не знает про «сейчас», это знание приходит снаружи (`today_local`).
    """
    return {
        "amount": "",
        "method": "transfer",
        "status": "paid",
        "date_value": today.strftime("%Y-%m-%d"),
        "comment": "",
    }
