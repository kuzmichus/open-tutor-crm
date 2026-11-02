"""Абстракция хранилища файлов (спека file-storage, design D2).

Один интерфейс на два бэкенда: локальный каталог сервера и S3-совместимый
бакет. Доменный код (загрузка, удаление, скачивание) работает только с
ключами объектов и не знает, куда именно лёг файл.

`download_url` возвращает `None` у хранилища, которое не умеет отдавать
временные ссылки: локальный файл отдаёт приложение (иначе проверку доступа
пришлось бы дублировать в веб-сервере), S3 — presigned URL.
"""

from abc import ABC, abstractmethod
from pathlib import Path

class Storage(ABC):
    """Хранилище объектов по ключу: запись, чтение, удаление, ссылка."""

    #: Имя бэкенда для метаданных (`files.backend`): `local` или `s3`.
    backend: str = ""

    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str) -> None:
        """Записывает объект по ключу; существующий объект заменяется."""

    @abstractmethod
    def open(self, key: str) -> bytes:
        """Читает объект целиком; нет объекта — исключение хранилища."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Удаляет объект; отсутствующий объект — не ошибка."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Есть ли объект по ключу."""

    @abstractmethod
    def download_url(
        self, key: str, filename: str, content_type: str
    ) -> str | None:
        """Временная ссылка на скачивание либо None — отдаёт приложение."""

    @abstractmethod
    def local_path(self, key: str) -> Path | None:
        """Путь к файлу на диске либо None — объект не на локальном диске."""
