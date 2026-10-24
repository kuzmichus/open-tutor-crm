"""Запись платежа: создание и правка (design D4, D11).

Платёж — строка `account_operations` с `kind='payment'`; баланс не
хранится и не пересчитывается здесь: он производный (design D3), поэтому
изменение суммы или статуса меняет баланс само.

Проверки дублируются (как в `group_writer`): форма могла быть отправлена
криво или устаревшими данными, валидация только на клиенте — не
валидация.

`occurred_at` — одно сортируемое поле (design D15): дата из формы плюс
текущее локальное время педагога в момент сохранения. Дата трактуется
как настенный день педагога и переводится в UTC общим `to_utc` — своего
сдвига у модуля нет.

Сервис не знает про FastAPI: на вход — сессия, ученик и очищенные
значения, на выход — платёж и список ошибок.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import to_utc
from app.finance.models.account_operation import AccountOperation
from app.finance.services.payment_form import validate_payment_data

CANCELLED_STATUS = "cancelled"


def _occurred_at(data: dict, tutor) -> datetime:
    """Момент операции: дата платежа + текущее время в зоне педагога (UTC).

    Референс показывает «22 окт. 2026, 01:31» при выбранной дате — то есть
    дату выбирают, а время берётся из момента ввода. Для сортировки этого
    достаточно; отдельная колонка «время перевода» не нужна (design D15).
    """
    from app.common.services.tutor_time import now_local

    local_now = now_local(tutor)
    local_value = datetime.combine(data["date"], local_now.time().replace(tzinfo=None))
    # Секунды и микросекунды обнуляем: подпись показывает минуты, и два
    # платежа одного дня должны сортироваться по времени ввода, а не по
    # случайным долям секунды.
    local_value = local_value.replace(second=0, microsecond=0)
    return to_utc(local_value, tutor)


def _same_day(value: datetime, data: dict, tutor) -> bool:
    """Совпадает ли хранимый момент с датой из формы (в зоне педагога).

    Нужен при правке: если дата не менялась, `occurred_at` сохраняет
    исходное время — история не должна переписывать время операции при
    правке комментария.
    """
    from app.common.services.tutor_time import to_local

    return to_local(value, tutor).date() == data["date"]


def has_refunds(db: Session, payment_id: str) -> bool:
    """Есть ли по платежу хотя бы один возврат (design D4).

    Отмена такого платежа запрещена: возврат уже вернул деньги, и статус
    «Отменено» сделал бы историю противоречивой — вернули то, чего не было.
    """
    return (
        db.scalars(
            select(AccountOperation.id)
            .where(
                AccountOperation.payment_id == payment_id,
                AccountOperation.kind == "refund",
            )
            .limit(1)
        ).first()
        is not None
    )


def create_payment(
    db: Session, student_id: str, data: dict, tutor
) -> tuple[AccountOperation | None, list[str]]:
    """Создаёт платёж; при ошибке ничего не сохраняет."""
    errors = validate_payment_data(data)
    if errors:
        db.rollback()
        return None, errors

    payment = AccountOperation(
        student_id=student_id,
        kind="payment",
        amount=data["amount"],
        occurred_at=_occurred_at(data, tutor),
        status=data["status"],
        method=data["method"],
        comment=data.get("comment") or None,
    )
    db.add(payment)
    db.commit()
    return payment, []


def update_payment(
    db: Session, payment: AccountOperation, data: dict, tutor
) -> list[str]:
    """Применяет данные формы к платежу; при ошибке откатывает изменения.

    Отмена платежа с возвратами отклоняется (design D4). Остальные поля
    правятся свободно: баланс производный и меняется сам.
    """
    errors = validate_payment_data(data)

    if (
        not errors
        and data["status"] == CANCELLED_STATUS
        and payment.status != CANCELLED_STATUS
        and has_refunds(db, payment.id)
    ):
        errors.append(
            "Нельзя отменить платёж, по которому оформлен возврат: "
            "сначала история вернула эти деньги."
        )

    if errors:
        db.rollback()
        return errors

    payment.amount = data["amount"]
    payment.method = data["method"]
    payment.status = data["status"]
    payment.comment = data.get("comment") or None
    # Дата не менялась — время операции остаётся исходным (design D15):
    # правка комментария не должна переставлять строку в истории.
    if not _same_day(payment.occurred_at, data, tutor):
        payment.occurred_at = _occurred_at(data, tutor)

    db.commit()
    return []
