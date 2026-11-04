"""Модель «Загруженный файл» (спека file-storage).

В таблице только метаданные: байты лежат в хранилище (локальный каталог или
S3-бакет), а здесь — ключ объекта и бэкенд, в котором объект записан.
Бэкенд хранится в строке, а не берётся из текущей настройки: смена
`FILES_BACKEND` не должна делать ранее загруженные файлы нечитаемыми.

Владелец — репетитор (`tutor_id`): файлы загружает он, а ученик и родитель
получают доступ через привязку файла к ДЗ (`HomeworkFile`).
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constraints import sql_string_in
from app.database import Base

# Закрытый список хранилищ: один источник истины для CHECK-ограничения и
# для фабрики (`app/files/services/storage_factory.py`).
FILE_BACKENDS = ("local", "s3")

# Размер ключа: `<uuid репетитора>/<32 hex><ext>` — с большим запасом.
MAX_STORAGE_KEY_LENGTH = 512
# Имя файла из формы: ограничение колонки, а не бизнес-правило — длинное
# имя обрезается при загрузке, а не отклоняется.
MAX_ORIGINAL_NAME_LENGTH = 255
MAX_CONTENT_TYPE_LENGTH = 128

class StoredFile(Base):
    """Метаданные одного загруженного файла.

    `storage_key` уникален: два объекта с одним ключом означали бы, что
    один файл затирает другой, и метаданные разошлись бы с содержимым.
    """

    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint(
            sql_string_in("backend", FILE_BACKENDS),
            name="ck_files_backend",
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
    backend: Mapped[str] = mapped_column(String(8), nullable=False)
    storage_key: Mapped[str] = mapped_column(
        String(MAX_STORAGE_KEY_LENGTH),
        nullable=False,
        unique=True,
        index=True,
    )
    original_name: Mapped[str] = mapped_column(
        String(MAX_ORIGINAL_NAME_LENGTH), nullable=False
    )
    content_type: Mapped[str] = mapped_column(
        String(MAX_CONTENT_TYPE_LENGTH), nullable=False
    )
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<StoredFile id={self.id} backend={self.backend!r} "
            f"name={self.original_name!r}>"
        )
