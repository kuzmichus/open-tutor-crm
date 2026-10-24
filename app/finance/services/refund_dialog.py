"""Контекст диалога возврата: сумма платежа и остаток к возврату (design D5).

Диалог показывает то, чего не знает форма: сумму платежа и сколько по нему
ещё можно вернуть. Остаток считается тем же сервисом, что и проверка при
записи (`refunds.refundable_amount`) — кнопка «Полный возврат» подставляет
ровно то число, которое сервис примет, а не пересчитанное в шаблоне.

При ошибке валидации присланные значения `data` перекрывают умолчания:
пользователь видит введённую сумму и причину (паттерн `payment_dialog`).

Сервис не знает про FastAPI: на вход — сессия, платёж и очищенные
значения, на выход — контекст шаблона.
"""

from sqlalchemy.orm import Session

from app.finance.models.account_operation import AccountOperation
from app.finance.services.refunds import refundable_amount, refunded_total
from app.student.services.presentation import student_full_name


def refund_dialog_context(
    db: Session,
    payment: AccountOperation,
    student,
    *,
    data: dict | None = None,
    errors: list[str] | None = None,
) -> dict:
    """Контекст `finance/_refund_dialog.html`.

    `data` — значения, введённые пользователем при ошибке. Сумма в `data`
    уже число (после разбора формы), а поле ввода ждёт строку.
    """
    values = {"amount": "", "comment": ""}
    if data is not None:
        amount = data.get("amount")
        values = {
            "amount": "" if amount is None else str(amount),
            "comment": data.get("comment") or "",
        }

    return {
        "refund_payment": payment,
        "refund_student": student,
        "refund_student_name": student_full_name(student),
        "refund_form": values,
        "refund_errors": errors or [],
        # Суммы считает сервис: шаблон не вычитает и не суммирует деньги.
        "refund_payment_amount": payment.amount,
        "refund_available": refundable_amount(db, payment),
        "refund_already": refunded_total(db, payment.id),
    }
