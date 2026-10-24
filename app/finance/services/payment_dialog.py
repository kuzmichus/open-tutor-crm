"""Контекст диалога платежа: значения полей, адрес сохранения, подписи.

Диалог один на создание и правку (`finance/_payment_dialog.html`):
`payment is None` — пустая форма с умолчаниями «Оплачено»/«Перевод» и
сегодняшней датой в зоне педагога; иначе — значения сохранённого платежа.

При ошибке валидации присланные значения `data` перекрывают и умолчания,
и сохранённые: пользователь должен увидеть то, что ввёл, а не сброшенную
форму (паттерн `lesson_form_context` и `slot/dialog_context`).

Ученик в контексте — только для подписи: полем формы он не передаётся
(design D11), поэтому шаблон выводит имя статичным текстом, а не селектом.

Сервис не знает про FastAPI: на вход — сессия, ученик, платёж и очищенные
значения, на выход — контекст шаблона.
"""

from datetime import date

from app.common.services.tutor_time import today_local
from app.finance.models.account_operation import (
    PAYMENT_METHODS,
    PAYMENT_METHOD_LABELS,
    PAYMENT_STATUSES,
    PAYMENT_STATUS_LABELS,
)
from app.finance.services.payment_form import empty_payment_form, payment_to_form

# Подписи полей диалога: шаблон не собирает их сам (AGENTS.md: серверные
# подписи живут в сервисе представления, а не в разметке).
PAYMENT_DIALOG_TITLES = {
    "create": "Новый платёж",
    "edit": "Платёж",
}


def _form_values(data: dict) -> dict:
    """Данные формы → значения полей (дата — строка `YYYY-MM-DD`).

    `data` приходит после разбора формы: дата в нём уже `date`, а сумма —
    число. Поля ввода ждут строк, иначе Jinja выведет `None` как «None».
    """
    value = data.get("date")
    return {
        "amount": "" if data.get("amount") is None else str(data["amount"]),
        "method": data.get("method") or "",
        "status": data.get("status") or "",
        "date_value": value.isoformat() if isinstance(value, date) else "",
        "comment": data.get("comment") or "",
    }


def payment_dialog_context(
    student,
    tutor,
    *,
    payment=None,
    data: dict | None = None,
    errors: list[str] | None = None,
) -> dict:
    """Контекст `finance/_payment_dialog.html`.

    `payment` — правимый платёж (`None` — создание); `data` — значения,
    введённые пользователем при ошибке; `errors` — сообщения валидации.
    """
    if payment is None:
        values = empty_payment_form(today_local(tutor))
        action = f"/tutor/students/{student.id}/payments"
        title = PAYMENT_DIALOG_TITLES["create"]
    else:
        values = payment_to_form(payment, tutor)
        action = f"/tutor/payments/{payment.id}"
        title = PAYMENT_DIALOG_TITLES["edit"]

    if data is not None:
        values = _form_values(data)

    return {
        "payment_student": student,
        "payment": payment,
        "payment_form": values,
        "payment_errors": errors or [],
        "payment_action": action,
        "payment_title": title,
        # Закрытые списки модели — один источник истины с CHECK-ограничениями.
        "payment_methods": PAYMENT_METHODS,
        "payment_method_labels": PAYMENT_METHOD_LABELS,
        "payment_statuses": PAYMENT_STATUSES,
        "payment_status_labels": PAYMENT_STATUS_LABELS,
    }
