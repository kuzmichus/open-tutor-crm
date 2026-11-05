"""Цепочка миграций должна иметь ровно одну голову.

`alembic upgrade head` — единственный способ создать схему на стенде
(`.taskdesk/stand-up.sh`): при двух головах команда падает с «Multiple head
revisions are present», и стенд не поднимается. Ветки задач отводятся от
одной базы и часто приносят свои ревизии, поэтому единственность головы —
инвариант, а не деталь отдельной задачи.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]


def _script_directory() -> ScriptDirectory:
    """Каталог ревизий из alembic.ini; база данных не нужна."""
    return ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))


def test_migrations_have_single_head():
    """Ровно одна голова: иначе `alembic upgrade head` не выполнится."""
    heads = _script_directory().get_heads()

    assert len(heads) == 1, f"Ожидалась одна голова миграций, получено: {heads}"


def test_migration_revisions_are_unique():
    """Идентификаторы ревизий не повторяются между файлами."""
    revisions = [rev.revision for rev in _script_directory().walk_revisions()]

    assert len(revisions) == len(set(revisions)), "Дублирующиеся revision id"


def test_every_revision_has_single_parent():
    """Нет merge-ревизий с несколькими родителями: проект ведёт линейную цепь."""
    for rev in _script_directory().walk_revisions():
        assert isinstance(rev.down_revision, str) or rev.down_revision is None, (
            f"Ревизия {rev.revision} имеет несколько родителей: {rev.down_revision}"
        )
