"""Модель «Операция счёта» (design D2).

Одна таблица на всё движение денег ученика: платёж, возврат и списание за
проведённый урок. Баланс — производная сумма со знаком (design D3), а не
колонка: денормализованный остаток пришлось бы обновлять в каждом пути
записи, и первая пропущенная ветка сделала бы число неверным без следа.

`tutor_id` в строке нет: владелец выводится из ученика, как у брони — из
окна. Изоляция — `get_owned_operation` одним `SELECT` с `JOIN students`.

Закрытые списки (AGENTS.md, п. 10) объявлены рядом с моделью: один источник
истины для `CheckConstraint`, для `options` селектов и для подписей.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Вид операции: платёж, возврат средств, списание за проведённый урок.
OPERATION_KINDS = ("payment", "refund", "lesson")

# Статус платежа. У возвратов и списаний статуса нет (design D4).
PAYMENT_STATUSES = ("paid", "pending", "cancelled")
PAYMENT_STATUS_LABELS = {
    "paid": "Оплачено",
    "pending": "Ожидает",
    "cancelled": "Отменено",
}

# Способ платежа.
PAYMENT_METHODS = ("transfer", "card", "online")
PAYMENT_METHOD_LABELS = {
    "transfer": "Перевод",
    "card": "Карта",
    "online": "Онлайн",
}

# Подписи видов операций для истории. У платежа видом операции в истории
# служит способ («Перевод»/«Карта»/«Онлайн») — так строка говорит, как
# пришли деньги, а не только «платёж».
OPERATION_KIND_LABELS = {
    "refund": "Возврат средств",
    "lesson": "Урок",
}
PAYMENT_FALLBACK_LABEL = "Платёж"

# В баланс входит только оплаченный платёж (design D3).
BALANCE_PAYMENT_STATUS = "paid"


def _sql_string_in(column: str, values: tuple[str, ...]) -> str:
    """`column IN ('a', 'b')` — строковый список для CHECK-ограничения."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class AccountOperation(Base):
    """Операция счёта ученика: платёж, возврат или списание за урок.

    `amount` всегда положителен (`ck_account_operations_amount`), знак
    выводится из `kind` одной формулой в `finance/services/balance.py`:
    хранить знак в сумме значило бы допустить положительный «возврат».

    `status` и `method` заполняются только у платежа; для возврата и
    списания они обязаны быть `NULL`. Инвариант держится и в БД
    (`ck_account_operations_payment_fields`), потому что иначе строка
    «урок» со статусом «Оплачено» попала бы в баланс дважды — как списание
    и как платёж.

    Пара «урок + ученик» уникальна среди списаний: частичный уникальный
    индекс `ux_account_operations_lesson_student` (см. миграцию) не даёт
    создать два списания по одному уроку для одного ученика. SQLite
    поддерживает частичные индексы, поэтому условие объявлено для обоих
    диалектов — как у `ux_bookings_active_slot`.

    Удаление ученика каскадом уносит его операции; удаление урока —
    его списания. `payment_id` объявлен `SET NULL`, а не `CASCADE`:
    удаление платежа в v1 не предусмотрено, но история возврата не должна
    исчезать от чужой ошибки в БД.
    """

    __tablename__ = "account_operations"
    __table_args__ = (
        CheckConstraint(
            _sql_string_in("kind", OPERATION_KINDS),
            name="ck_account_operations_kind",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_account_operations_amount",
        ),
        CheckConstraint(
            "status IS NULL OR " + _sql_string_in("status", PAYMENT_STATUSES),
            name="ck_account_operations_status",
        ),
        CheckConstraint(
            "method IS NULL OR " + _sql_string_in("method", PAYMENT_METHODS),
            name="ck_account_operations_method",
        ),
        # Статус и способ — только у платежа (design D4).
        CheckConstraint(
            "kind = 'payment' OR (status IS NULL AND method IS NULL)",
            name="ck_account_operations_payment_fields",
        ),
        Index(
            "ux_account_operations_lesson_student",
            "lesson_id",
            "student_id",
            unique=True,
            sqlite_where=text("kind = 'lesson'"),
            postgresql_where=text("kind = 'lesson'"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Владелец выводится из ученика; операция без ученика не существует.
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    # Сумма в рублях, всегда больше нуля: знак выводится из вида операции.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    # Момент операции в UTC: дата платежа/возврата плюс время сохранения,
    # у списания — начало урока (design D15). SQLite теряет tzinfo, чтения
    # нормализуются через `as_utc`.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    # Только у платежа (design D4); у остальных видов — NULL.
    status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Комментарий платежа или причина возврата.
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Списание за урок; каскад: удаление урока снимает его списания.
    lesson_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Возврат ссылается на платёж, по которому он оформлен.
    payment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("account_operations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<AccountOperation id={self.id} kind={self.kind!r} "
            f"amount={self.amount} student_id={self.student_id!r}>"
        )
