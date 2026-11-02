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

# Адрес исходного кода — для ссылки в подвале сервиса
# (`app/templates/_footer_signature.html`). Хранится рядом с версией: обе
# подписи — про сам проект, и в шаблонах их литералов быть не должно.
__repository_url__ = "https://github.com/kuzmichus/open-tutor-crm/"
