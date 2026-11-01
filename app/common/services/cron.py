"""Реестр и запуск заданий cron (скрипт `cron.py` в корне).

Скрипт запускается внешним планировщиком раз в минуту и на каждом прогоне
выполняет все задания из `TASKS`. Схема (design D5 change'а unmarked-lessons):

- задание — пара `(имя, callable)`, callable получает `Session` и возвращает
  число изменений (для лога);
- коммит — обязанность runner'а: каждое задание живёт в своей транзакции,
  падение одного пишет ошибку в лог, откатывает своё и не мешает остальным;
- задания обязаны быть идемпотентными: условие отбора считается от «сейчас»,
  поэтому наложение прогонов и повторный запуск безопасны.

Логику конкретных заданий держат доменные сервисы (например,
`app/lesson/services/auto_complete.py`, `app/messenger/services/daily_digest.py`)
— здесь только общий механизм.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.database import SessionLocal

# Регистрация всех моделей на Base.metadata — как в `init_db()`. Доменный
# сервис тянет только нужную ему модель (например, `Lesson`), а её FK
# (`lessons.series_id` → `lesson_series`) резолвится лишь при импорте
# второй стороны; вне веб-приложения агрегатор `app.models` никто не
# импортирует, и первый же flush падал бы с NoReferencedTableError.
from app import models  # noqa: F401

from app.lesson.services.auto_complete import auto_complete_finished_lessons
from app.messenger.services.daily_digest import run_daily_digests

if TYPE_CHECKING:  # только для аннотации: циклический импорт не нужен
    from sqlalchemy.orm import Session

logger = logging.getLogger("cron")

# Аргумент — сессия, результат — число изменений (для строки лога).
TaskCallable = Callable[["Session"], int]

# Реестр заданий: пополняется парами (имя, функция) из доменных сервисов.
TASKS: list[tuple[str, TaskCallable]] = [
    ("lesson.auto_complete", auto_complete_finished_lessons),
    ("messenger.daily_digest", run_daily_digests),
]


def run_tasks() -> int:
    """Выполняет все задания из `TASKS`; возвращает 0, либо 1 при падении.

    Каждое задание — своя сессия и транзакция: упавшее откатывается,
    остальные выполняются и коммитятся дальше.
    """
    failures = 0
    for name, run in TASKS:
        with SessionLocal() as db:
            try:
                changed = run(db)
                db.commit()
            except Exception:
                # Чужое исключение — штатная ветка runner'а: задание
                # изолировано, остальные продолжают работать.
                db.rollback()
                failures += 1
                logger.exception("задание %s упало", name)
            else:
                logger.info("задание %s: изменений %s", name, changed)
    return 1 if failures else 0
