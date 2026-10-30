"""Модель «Расход репетитора».

Расход — трата самого репетитора (аренда, реклама, подписки), а не движение
по счёту ученика: он живёт в отдельной таблице и в баланс ученика не входит.
`AccountOperation` не расширялась новым видом: операции счёта ограничены
спекой student-finance (платёж/возврат/списание за урок), и «расход» в этой
тройке сломал бы формулу баланса — у траты нет ученика.

Владелец — сам репетитор (`tutor_id`): в отличие от операций счёта, где
владелец выводится из ученика, здесь владельца выводить не из чего.
Изоляция — `get_owned_expense` одним `SELECT` по `id` и `tutor_id`.

Категории — закрытый список (AGENTS.md, п. 10): один источник истины для
`CheckConstraint`, для `options` селекта и для словаря подписей. Набор —
по референсу диалога расхода, порядок — алфавит подписей.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constraints import sql_string_in
from app.database import Base

# Категория расхода; «Прочее» — умолчание формы.
EXPENSE_CATEGORIES = (
    "rent",
    "taxes",
    "equipment",
    "training",
    "software",
    "other",
    "ads",
    "communication",
    "transport",
    "materials",
)

EXPENSE_CATEGORY_LABELS = {
    "rent": "Аренда",
    "taxes": "Налоги",
    "equipment": "Оборудование",
    "training": "Повышение квалификации",
    "software": "Программное обеспечение",
    "other": "Прочее",
    "ads": "Реклама",
    "communication": "Связь",
    "transport": "Транспорт",
    "materials": "Учебные материалы",
}

DEFAULT_EXPENSE_CATEGORY = "other"


class Expense(Base):
    """Трата репетитора: категория, сумма и день траты.

    `amount` всегда положителен: расход по смыслу уменьшает итог, и хранить
    знак значило бы допустить «положительный расход». В сводке вычитается
    из чистого дохода («Осталось репетитору»).

    `spent_at` — момент траты в UTC (дата из формы плюс время сохранения,
    как `occurred_at` платежа): сводка фильтрует расходы тем же окном
    `[start, end)`, что и операции счёта. SQLite теряет tzinfo, чтения
    нормализуются через `as_utc`.

    Удаление репетитора каскадом уносит его расходы.
    """

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount"),
        CheckConstraint(
            sql_string_in("category", EXPENSE_CATEGORIES),
            name="ck_expenses_category",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    # Что именно куплено: необязательно, но без него строка «Прочее 3 000 ₽»
    # в истории ничего не скажет через месяц.
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    spent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
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
            f"<Expense id={self.id} category={self.category!r} "
            f"amount={self.amount} tutor_id={self.tutor_id!r}>"
        )
