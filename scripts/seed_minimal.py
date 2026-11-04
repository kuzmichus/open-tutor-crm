"""Минимальное наполнение стенда: пустая база с одной карточкой репетитора.

Пресет ``minimal`` из .taskdesk/seed.sh: без учеников, уроков и платежей —
только вход ``demo@example.com`` / ``12345678``. Логика сброса и создания
репетитора берётся из seed_demo, чтобы креды и карточка жили в одном месте.
"""

import sys
from pathlib import Path

# как и seed_demo: работаем и как ``python scripts/seed_minimal.py``,
# и как импорт пакета — корень проекта должен попасть в sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from scripts.seed_demo import (  # noqa: E402
    TUTOR_EMAIL,
    TUTOR_PASSWORD,
    _create_tutor,
    _reset_demo_data,
)


def main() -> None:
    """Сброс демо-данных и карточка репетитора; идемпотентно."""
    with SessionLocal() as db:
        _reset_demo_data(db, TUTOR_EMAIL)
        tutor = _create_tutor(db)
        db.commit()
    print(f"Вход: {tutor.email} / {TUTOR_PASSWORD}")


if __name__ == "__main__":
    main()
