"""Версия приложения берётся из `pyproject.toml` и нигде не дублируется.

Второй источник версии в коде означал бы, что `app.version`, git-тег релиза
и опубликованный образ рано или поздно разойдутся. Тест читает манифест
самостоятельно (а не сравнивает константу с самой собой), поэтому остаётся
зелёным при смене версии и падает, если литерал вернут в код.
"""

import tomllib
from pathlib import Path

from main import app

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

def _manifest_version() -> str:
    with PYPROJECT.open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)["project"]["version"]

def test_openapi_version_matches_manifest():
    """`info.version` в OpenAPI совпадает с версией из манифеста проекта."""
    assert app.openapi()["info"]["version"] == _manifest_version()

def test_app_version_matches_manifest():
    """`app.version` совпадает с версией из манифеста проекта."""
    assert app.version == _manifest_version()
