"""Open Tutor CRM — пакет приложения."""

import tomllib
from pathlib import Path

# Версия — только из манифеста проекта: второй источник в коде означал бы,
# что app.version и опубликованный образ рано или поздно разойдутся.
# importlib.metadata не подходит: приложение не устанавливается как пакет
# (нет [build-system], в Dockerfile --no-install-project), поэтому читаем файл.
# pyproject.toml копируется в рантайм-стадию Dockerfile именно ради этого.
_PYPROJECT_PATH = Path(__file__).resolve().parent.parent / "pyproject.toml"

with _PYPROJECT_PATH.open("rb") as _pyproject_file:
    __version__ = tomllib.load(_pyproject_file)["project"]["version"]
