"""Модель «Файл домашнего задания» (спека homework-management).

Связь «файл ↔ ДЗ» отдельной строкой: один файл может быть прикреплён к
нескольким заданиям, а порядок в списке держит `position` — без него порядок
строк в SELECT не гарантирован, а репетитор прикрепляет файлы в осмысленной
последовательности (паттерн `HomeworkAnswerLink`).
"""

from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class HomeworkFile(Base):
    """Один файл в списке материалов домашнего задания."""

    __tablename__ = "homework_files"
    __table_args__ = (
        UniqueConstraint("homework_id", "file_id", name="uq_homework_files_pair"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    homework_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("homework.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<HomeworkFile id={self.id} homework_id={self.homework_id!r} "
            f"file_id={self.file_id!r} position={self.position}>"
        )
