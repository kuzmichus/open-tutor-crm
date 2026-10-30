"""Модель «Ссылка на работу в ответе ученика» (спека homework-management).

Ответ может содержать несколько ссылок (макет: «+ Добавить ссылку»), поэтому
ссылка — дочерняя строка ответа с каскадным удалением. Порядок списка держит
`position`: без него порядок строк в SELECT не гарантирован, а ученик
прикладывает файлы в осмысленной последовательности. Ссылки — только на
облачные хранилища (http/https): файлы в этой итерации не загружаются.
"""

from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Размер колонки совпадает с `recording_url`/`meeting_url`: адрес облачного
# хранилища с параметрами доступа укладывается с запасом.
MAX_LINK_LENGTH = 500


class HomeworkAnswerLink(Base):
    """Одна ссылка на работу в ответе ученика, с номером в списке."""

    __tablename__ = "homework_answer_links"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    answer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("homework_answers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(MAX_LINK_LENGTH), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<HomeworkAnswerLink id={self.id} answer_id={self.answer_id!r} "
            f"position={self.position}>"
        )
