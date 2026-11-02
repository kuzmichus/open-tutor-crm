"""Прикрепление загруженных файлов к домашнему заданию (design D5).

Связь «файл ↔ ДЗ» создаётся после того, как у записи ДЗ есть id: файлы
сохраняются пачкой, `position` продолжает уже существующий список.

Ошибка любого файла отменяет пачку целиком: уже записанные объекты удаляются
из хранилища, строки не остаются. Вызывающая вьюха откатывает транзакцию —
поэтому здесь нет коммита, а «половины» набора не бывает.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.files.models.homework_file import HomeworkFile
from app.files.models.stored_file import StoredFile
from app.files.services.storage import Storage
from app.files.services.storage_factory import storage_for_backend
from app.files.services.upload import save_upload

logger = logging.getLogger(__name__)

def _next_position(db: Session, homework_id: str) -> int:
    """Следующий номер в списке файлов ДЗ: после последнего прикреплённого."""
    last = db.scalar(
        select(func.max(HomeworkFile.position)).where(
            HomeworkFile.homework_id == homework_id
        )
    )
    return (last + 1) if last is not None else 0

def _discard(files: list[StoredFile], storage: Storage | None) -> None:
    """Убирает объекты неудавшейся пачки: строки откатит транзакция."""
    for file in files:
        store = storage if storage is not None else storage_for_backend(file.backend)
        try:
            store.delete(file.storage_key)
        except Exception:  # noqa: BLE001 — уборка не должна скрывать исходную ошибку
            logger.exception(
                "Не удалось убрать объект файла %s (%s)",
                file.id,
                file.storage_key,
            )

async def attach_files(
    db: Session,
    tutor_id: str,
    homework_id: str,
    uploads: list,
    storage: Storage | None = None,
) -> tuple[list[StoredFile], list[str]]:
    """Сохраняет пачку файлов и привязывает их к ДЗ.

    Возвращает `(файлы, ошибки)`. При ошибке возвращается пустой список
    файлов: набор прикрепляется целиком или не прикрепляется вовсе.
    """
    saved: list[StoredFile] = []
    position = _next_position(db, homework_id)
    for upload in uploads:
        file, errors = await save_upload(db, tutor_id, upload, storage)
        if errors:
            _discard(saved, storage)
            return [], errors
        # id строки выдаётся при flush: без него связь `homework_files`
        # получила бы file_id = NULL и упала на NOT NULL.
        db.flush()
        db.add(
            HomeworkFile(
                homework_id=homework_id,
                file_id=file.id,
                position=position,
            )
        )
        saved.append(file)
        position += 1
    return saved, []
