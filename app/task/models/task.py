"""Модель «Задача» — дело репетитора на канбан-доске.

Задача принадлежит репетитору целиком (`tutor_id`): ответственного
исполнителя в интерфейсе нет — задачи ставит себе сам педагог, поэтому
владелец выводится прямо из колонки, без JOIN (в отличие от урока и
брони, где владелец выводится из цели).

Этап — закрытый список (AGENTS.md, п. 10): один источник истины для
CHECK-ограничения в БД, для options селекта и для подписей колонок.
Приоритет — такой же закрытый список.

`completed_at` хранит момент перехода в «Готово»: по нему блок «Завершено»
списка сортируется (последняя завершённая — сверху). Значение сбрасывается,
когда задачу возвращают из «Готово», — иначе дата завершения врала бы.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constraints import sql_string_in
from app.database import Base

# Этапы доски: порядок кортежа — порядок колонок слева направо.
TASK_STAGES = ("new", "in_progress", "review", "done")
TASK_STAGE_LABELS = {
    "new": "Новые",
    "in_progress": "В работе",
    "review": "На проверке",
    "done": "Готово",
}

# Приоритет: порядок кортежа — от низкого к высокому, он же порядок
# options селекта. Умолчание формы — «Средний».
TASK_PRIORITIES = ("low", "medium", "high")
TASK_PRIORITY_LABELS = {
    "low": "Низкий",
    "medium": "Средний",
    "high": "Высокий",
}

# Этап, при котором задача считается завершённой (блок «Завершено» списка).
TASK_DONE_STAGE = "done"


class Task(Base):
    """Задача репетитора: этап, приоритет, срок и описание.

    Ученики привязываются отдельной таблицей `task_students` (связь
    многие-ко-многим): одна задача может касаться нескольких учеников,
    и удаление ученика не должно уничтожать задачу — связка удаляется
    каскадом, сама задача остаётся.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            sql_string_in("stage", TASK_STAGES),
            name="ck_tasks_stage",
        ),
        CheckConstraint(
            sql_string_in("priority", TASK_PRIORITIES),
            name="ck_tasks_priority",
        ),
        # Доска всегда читается владельцем с сортировкой по сроку —
        # составной индекс закрывает выборку целиком.
        Index("ix_tasks_tutor_stage", "tutor_id", "stage"),
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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Этап доски и приоритет — значения из закрытых списков выше.
    stage: Mapped[str] = mapped_column(
        String(16), nullable=False, default="new", index=True
    )
    priority: Mapped[str] = mapped_column(
        String(8), nullable=False, default="medium"
    )
    # Срок — календарная дата в зоне педагога (не момент времени):
    # «сделать до 26 октября» не имеет часа, и часовой пояс тут не нужен.
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # Момент перехода в «Готово»; NULL — задача не завершена.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} stage={self.stage!r}>"
