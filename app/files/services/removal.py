"""Удаление файлов: объект в хранилище и строка метаданных (design D6).

Порядок важен: сначала объект в хранилище, потом строка в БД. Если удалить
строку первой, а хранилище не ответит, объект останется навсегда и никто уже
не знает его ключ — «сироту» нечем убрать. Обратная ошибка (сбой хранилища)
оставляет метаданные без объекта; такая строка отдаёт 404 при скачивании, но
остаётся видимой в списке. Поэтому при сбое хранилища ошибка логируется, а
строка всё равно удаляется: «битая» запись в интерфейсе хуже, чем запись в
журнале.

Хранилище выбирается по `files.backend`, а не по текущему env: файл мог быть
загружен до смены `FILES_BACKEND` (design D1).
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.files.models.homework_file import HomeworkFile
from app.files.models.stored_file import StoredFile
from app.files.services.storage import Storage
from app.files.services.storage_factory import storage_for_backend
from app.homework.models.homework import Homework

logger = logging.getLogger(__name__)

def _storage(file: StoredFile, storage: Storage | None) -> Storage:
    """Хранилище файла: явное (тесты) либо записанное в метаданных."""
    return storage if storage is not None else storage_for_backend(file.backend)

def _delete_object(file: StoredFile, storage: Storage | None) -> None:
    """Удаляет объект; отсутствующий объект — не ошибка."""
    try:
        _storage(file, storage).delete(file.storage_key)
    except Exception:  # noqa: BLE001 — сбой хранилища не должен блокировать удаление
        logger.exception(
            "Не удалось удалить объект файла %s (%s)", file.id, file.storage_key
        )

def delete_file(
    db: Session,
    file: StoredFile,
    storage: Storage | None = None,
) -> None:
    """Удаляет объект и строку; коммита не делает (его держит вызывающий)."""
    _delete_object(file, storage)
    db.delete(file)

def delete_files(
    db: Session,
    files: list[StoredFile],
    storage: Storage | None = None,
) -> None:
    """Удаляет пачку файлов; коммита не делает."""
    for file in files:
        delete_file(db, file, storage)

def files_of_homework(db: Session, homework_id: str) -> list[StoredFile]:
    """Файлы одного ДЗ в порядке прикрепления."""
    return files_of_homeworks(db, [homework_id]).get(homework_id, [])

def files_of_homeworks(
    db: Session, homework_ids: list[str]
) -> dict[str, list[StoredFile]]:
    """Файлы пачки ДЗ одним SELECT, сгруппированные по ДЗ (без N+1)."""
    if not homework_ids:
        return {}
    rows = db.execute(
        select(HomeworkFile.homework_id, StoredFile)
        .join(StoredFile, HomeworkFile.file_id == StoredFile.id)
        .where(HomeworkFile.homework_id.in_(homework_ids))
        .order_by(HomeworkFile.position, HomeworkFile.id)
    ).all()
    grouped: dict[str, list[StoredFile]] = {}
    for homework_id, file in rows:
        grouped.setdefault(homework_id, []).append(file)
    return grouped

def delete_homework_files(
    db: Session,
    lesson_ids: list[str],
    storage: Storage | None = None,
) -> int:
    """Удаляет объекты файлов ДЗ уроков перед каскадным удалением уроков.

    БД снимет строки `homework_files` и `files` каскадом (FK `ondelete=
    CASCADE`), но объекты в хранилище каскад не тронет — их убираем здесь.
    Возвращает число удалённых объектов.
    """
    if not lesson_ids:
        return 0
    homework_ids = list(
        db.scalars(
            select(Homework.id).where(Homework.lesson_id.in_(lesson_ids))
        ).all()
    )
    files = [f for group in files_of_homeworks(db, homework_ids).values() for f in group]
    for file in files:
        _delete_object(file, storage)
    return len(files)
