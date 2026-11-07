"""Хранилище лендинга на диске: файлы, без веба и без базы.

Раскладка каталога `LANDING_ROOT`:

```
landing/
  draft.html        черновик (пишет редактор, показывает предпросмотр)
  index.html        опубликованная страница → GET /
  index.prev.html   бэкап прошлой публикации
  assets/<uuid>.<ext>  картинки редактора, публично /landing-assets/...
```

Почему диск, а не `FILES_*`/S3: лендинг один на установку, его HTML —
обычный файл, а публичная отдача не должна зависеть от бэкенда загрузок.

Каталоги создаются лениво, при первой записи: чтения на пустом корне
отвечают «нет» без исключений, поэтому свежая установка не требует
подготовки каталога. Запись идёт через временный файл и `os.replace` —
атомарная замена не оставляет половину страницы под итоговым именем, если
процесс упал посреди записи (тот же приём, что в локальном хранилище
файлов).

Имя ассета генерирует сервер: `uuid4` и расширение исходного файла.
Пользовательское имя в путь не попадает — только расширение из allowlist,
поэтому обход каталога через имя файла невозможен.
"""

import os
import re
from pathlib import Path
from uuid import uuid4

from app.config import settings

# Расширения картинок, которые принимает редактор. Список совпадает с
# маршрутом отдачи ассетов (`app/landing/views/assets.py`): сохранить файл,
# который потом нельзя открыть по ссылке, бессмысленно.
ALLOWED_ASSET_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "webp", "svg"})

# Имя ассета, которое принимает публичный маршрут: `uuid4` и расширение из
# allowlist. Шаблон строгий — он же защита от обхода каталога: точки,
# слэши и прочий пользовательский ввод в имя не проходят.
ASSET_NAME_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"\.(png|jpe?g|gif|webp|svg)$"
)
_ASSET_NAME_RE = re.compile(ASSET_NAME_PATTERN)


def is_asset_name(name: str) -> bool:
    """True, если имя похоже на сгенерированное `save_asset`."""
    return _ASSET_NAME_RE.fullmatch(name) is not None


class LandingStorage:
    """Файлы лендинга в каталоге `root`; каталог создаётся при записи."""

    draft_name = "draft.html"
    index_name = "index.html"
    prev_name = "index.prev.html"
    assets_dirname = "assets"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    # --- Пути -------------------------------------------------------------

    @property
    def draft_path(self) -> Path:
        """Черновик страницы."""
        return self.root / self.draft_name

    @property
    def index_path(self) -> Path:
        """Опубликованная страница — её отдаёт `GET /`."""
        return self.root / self.index_name

    @property
    def prev_path(self) -> Path:
        """Бэкап прошлой публикации; при `unpublish` не трогается."""
        return self.root / self.prev_name

    @property
    def assets_dir(self) -> Path:
        """Каталог картинок редактора."""
        return self.root / self.assets_dirname

    def asset_path(self, name: str) -> Path:
        """Путь ассета по имени; имя с разделителями — `ValueError`.

        Имя формирует сервер, но проверка стоит у последней границы, где
        строка превращается в путь на диске (как в локальном хранилище
        файлов): запрос `/landing-assets/...` приходит извне.
        """
        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\x00" in name
        ):
            raise ValueError(f"Недопустимое имя ассета: {name!r}")
        return self.assets_dir / name

    # --- Черновик ---------------------------------------------------------

    def has_draft(self) -> bool:
        """Есть ли черновик страницы."""
        return self.draft_path.is_file()

    def read_draft_html(self) -> str | None:
        """HTML черновика; файла нет — `None`, а не исключение."""
        try:
            return self.draft_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def save_draft(self, html: str) -> None:
        """Сохраняет черновик; каталог создаётся при первой записи."""
        self._write_atomic(self.draft_path, html.encode("utf-8"))

    # --- Публикация -------------------------------------------------------

    def has_published(self) -> bool:
        """Есть ли опубликованная страница."""
        return self.index_path.is_file()

    def publish(self) -> bool:
        """Публикует черновик: `index.html` → `index.prev.html`, затем копия.

        Черновик остаётся на месте: редактор продолжает показывать
        предпросмотр и править страницу после публикации. Бэкап
        перезаписывается — хранится ровно одна прошлая версия.

        Возвращает `False`, если публиковать нечего (черновика нет).
        """
        if not self.has_draft():
            return False
        if self.has_published():
            self._write_atomic(self.prev_path, self.index_path.read_bytes())
        self._write_atomic(self.index_path, self.draft_path.read_bytes())
        return True

    def unpublish(self) -> None:
        """Убирает страницу с публикации; бэкап и черновик не трогаются."""
        self.index_path.unlink(missing_ok=True)

    # --- Ассеты -----------------------------------------------------------

    def list_assets(self) -> list[str]:
        """Имена файлов в `assets/`; каталога нет — пустой список."""
        if not self.assets_dir.is_dir():
            return []
        return sorted(
            path.name for path in self.assets_dir.iterdir() if path.is_file()
        )

    def save_asset(self, filename: str, content: bytes) -> str:
        """Сохраняет картинку под сгенерированным именем и возвращает его.

        Расширение берётся из исходного имени (регистр нормализуется), а
        основа — `uuid4`: одинаковые `photo.png` не перезаписывают друг
        друга, а имя из формы не попадает в путь.
        """
        extension = Path(filename).suffix.lstrip(".").lower()
        if extension not in ALLOWED_ASSET_EXTENSIONS:
            raise ValueError(
                f"Недопустимое расширение ассета: {filename!r}"
            )
        name = f"{uuid4()}.{extension}"
        self._write_atomic(self.asset_path(name), content)
        return name

    def remove_asset(self, name: str) -> None:
        """Удаляет ассет; отсутствующий файл — не ошибка."""
        self.asset_path(name).unlink(missing_ok=True)

    # --- Запись -----------------------------------------------------------

    def _write_atomic(self, path: Path, data: bytes) -> None:
        """Пишет файл через временный файл и атомарную замену."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
        finally:
            # Оборванная запись не должна оставлять мусор в каталоге.
            tmp.unlink(missing_ok=True)


def get_storage() -> LandingStorage:
    """Хранилище по текущей настройке `LANDING_ROOT`.

    Создаётся на каждый вызов, а не кэшируется: объект дешёвый, а тесты и
    владелец сервера меняют `settings.landing_root` без перезапуска
    процесса (в отличие от клиента S3 в модуле файлов).
    """
    return LandingStorage(settings.landing_root)
