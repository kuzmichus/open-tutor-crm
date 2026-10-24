"""Контекст вкладки «Платежи»: баланс, платежи, история, баннер (design D11).

Панель — не форма: каждый её элемент — самостоятельный запрос, поэтому
контекст не содержит ни действия POST карточки, ни скрытых полей. Всё,
что показывает панель, считается сервисами модуля и приходит готовым:
шаблон не суммирует деньги и не решает, можно ли оформить возврат.

`refundable` у платежа — остаток к возврату (design D5), `can_refund` —
решение сервиса, а не шаблона: возврат возможен только по оплаченному
платежу с ненулевым остатком.

Сервис не знает про FastAPI: на вход — сессия, ученик и репетитор, на
выход — контекст шаблона.
"""

from sqlalchemy.orm import Session

from app.finance.models.account_operation import BALANCE_PAYMENT_STATUS
from app.finance.services.balance import balance
from app.finance.services.operations import student_history, student_payments
from app.finance.services.recalculate import has_missing_charges
from app.finance.services.refunds import refund_totals_for_student
from app.student.services.presentation import student_full_name


def panel_context(db: Session, student, tutor) -> dict:
    """Контекст `finance/_panel.html`.

    История ограничена последними 20 строками (`operations.HISTORY_LIMIT`):
    пагинации в v1 нет (design: Non-Goals). Платежи показываются все — их
    за месяц немного, а отменённый платёж репетитор должен видеть, чтобы
    исправить статус.
    """
    payments = student_payments(db, student.id)
    refunded = refund_totals_for_student(db, student.id)

    payment_rows = []
    for payment in payments:
        refundable = payment.amount - refunded.get(payment.id, 0)
        payment_rows.append(
            {
                "payment": payment,
                "refundable": refundable,
                # Возврат — только по полученным деньгам и только пока есть
                # что возвращать: «Ожидает» ещё не оплачен.
                "can_refund": (
                    payment.status == BALANCE_PAYMENT_STATUS and refundable > 0
                ),
            }
        )

    return {
        "finance_student": student,
        "finance_student_name": student_full_name(student),
        "finance_tutor": tutor,
        "finance_balance": balance(db, student.id),
        "finance_payments": payment_rows,
        "finance_history": student_history(db, student.id),
        # Баннер вместо data-миграции (design D8): расхождение видно, пока
        # репетитор не нажмёт «Пересчитать».
        "finance_needs_recalculate": has_missing_charges(
            db, tutor.id, student.id
        ),
    }
