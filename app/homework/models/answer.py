"""Модель «Ответ ученика на домашнее задание» (спека homework-management).

Ответ живёт отдельно от записи ДЗ и в соотношении 1:1 с ней: UNIQUE на
`homework_id` и каскадное удаление вместе с ДЗ (а значит и с уроком).
Текст необязателен — ответом могут быть только ссылки на работу; пустым
должен быть хотя бы один из компонентов, но не оба: это проверяет
валидация формы, а не БД.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class HomeworkAnswer(Base):
    """Ответ ученика на домашнее задание: текст и дата последней отправки.

    Ссылки на работу живут отдельными строками (`HomeworkAnswerLink`) —
    их список правится целиком при каждой отправке. `submitted_at`
    хранится в UTC и обновляется при каждой отправке: это дата последнего
    ответа, а не первого.
    """

    __tablename__ = "homework_answers"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    homework_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("homework.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<HomeworkAnswer id={self.id} homework_id={self.homework_id!r}>"
