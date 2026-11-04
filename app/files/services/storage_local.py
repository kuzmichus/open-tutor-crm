"""Локальное хранилище: каталог на диске сервера (design D2).

Ключ объекта трактуется как относительный путь внутри корня. Обязательная
проверка «итоговый путь внутри корня» — защита от ключа вида
`../../etc/passwd`: ключ формирует сервер, но проверка нужна именно здесь,
у последней границы, где строка превращается в путь на диске.

Запись идёт через временный файл в том же каталоге и `os.replace`: атомарная
замена не оставляет половину файла под итоговым именем, если процесс упал
посреди записи.
"""

import os
from pathlib import Path
from uuid import uuid4

from app.files.services.storage import Storage

class LocalStorage(Storage):
    """Хранилище в каталоге `root`; корень создаётся при инициализации."""

    backend = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        """Путь объекта; ключ вне корня — `ValueError`.

        `resolve()` раскрывает `..` и симлинки, после чего путь проверяется
        на принадлежность корню: сравнение по префиксу строки пропустило бы
        `/data/files-secret` при корне `/data/files`.
        """
        candidate = (self.root / key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError(f"Ключ вне корня хранилища: {key!r}")
        return candidate

    def save(self, key: str, data: bytes, content_type: str) -> None:
        """Пишет объект через временный файл и атомарную замену."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
        finally:
            # Оборванная запись не должна оставлять мусор в каталоге.
            tmp.unlink(missing_ok=True)

    def open(self, key: str) -> bytes:
        """Читает объект целиком; нет файла — `FileNotFoundError`."""
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        """Удаляет объект; отсутствующий файл — не ошибка."""
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        """Есть ли файл по ключу."""
        return self._path(key).is_file()

    def download_url(
        self, key: str, filename: str, content_type: str
    ) -> str | None:
        """None: локальный файл отдаёт приложение с проверкой сессии."""
        return None

    def local_path(self, key: str) -> Path:
        """Путь на диске — его отдаёт `FileResponse` вьюхи скачивания."""
        return self._path(key)
