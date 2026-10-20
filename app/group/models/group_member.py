"""Модель «Участник группы»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GroupMember(Base):
    """Членство ученика в группе: дата вступления и индивидуальная цена.

    Ученик состоит в группе не более одного раза (`uq_group_members_pair`).
    `price_override IS NULL` означает «оплата по общей цене группы».
    Удаление группы или ученика каскадом удаляет членство: каскад обеих
    FK, сами записи-родители не затрагиваются.
    """

    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "student_id", name="uq_group_members_pair"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    group_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Дата вступления: по умолчанию — момент добавления; меняется
    # во вкладке «Настройки» группы.
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    # Индивидуальная цена за урок, рубли. NULL — по общей цене группы.
    price_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<GroupMember id={self.id} group_id={self.group_id!r} "
            f"student_id={self.student_id!r}>"
        )
