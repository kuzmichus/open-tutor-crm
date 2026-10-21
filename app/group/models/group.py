"""Модель «Группа»."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Group(Base):
    """Учебная группа репетитора: несколько учеников на один урок.

    Группа принадлежит репетитору (`tutor_id`): при удалении репетитора
    его группы удаляются каскадом, при удалении группы каскадом уходит её
    состав (`group_members`), сами ученики не затрагиваются.
    """

    __tablename__ = "groups"

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
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Цена за урок с человека, рубли. NULL — цена не задана, в карточке
    # блок цены не показывается.
    price_per_lesson: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Постоянная ссылка на встречу (видеоконференция).
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Заметки к группе: видит только репетитор, ученикам не показываются.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Цвет цели для календаря: назначается при создании из палитры
    # `app/common/colors.py` и далее не меняется.
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
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
        return f"<Group id={self.id} name={self.name!r}>"
