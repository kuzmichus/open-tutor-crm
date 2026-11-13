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
`app/lesson/services/auto_complete.py`, `app/messenger/services/daily_digest.py`,
`app/messenger/services/birthday_digest.py`) — здесь только общий механизм.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.database import SessionLocal

# Регистрация всех моделей на Base.metadata — как в alembic/env.py и тестовом
# conftest. Доменный сервис тянет только нужную ему модель (например, `Lesson`), а её FK
# (`lessons.series_id` → `lesson_series`) резолвится лишь при импорте
# второй стороны; вне веб-приложения агрегатор `app.models` никто не
# импортирует, и первый же flush падал бы с NoReferencedTableError.
from app import models  # noqa: F401

from app.gcalendar.services.reconcile import reconcile_all
from app.lesson.services.auto_complete import auto_complete_finished_lessons
from app.messenger.services.birthday_digest import notify_birthday_digest
from app.messenger.services.daily_digest import run_daily_digests
from app.messenger.services.lesson_reminders import run_lesson_reminders

if TYPE_CHECKING:  # только для аннотации: циклический импорт не нужен
    from sqlalchemy.orm import Session

logger = logging.getLogger("cron")

# Аргумент — сессия, результат — число изменений (для строки лога).
TaskCallable = Callable[["Session"], int]

# Реестр заданий: пополняется парами (имя, функция) из доменных сервисов.
#
# Порядок значим для напоминаний об уроке: они обязаны выполняться **до**
# `lesson.auto_complete`. Автозавершение закрывает урок через 24 часа после
# его окончания, а выборка напоминаний берёт только `status='planned'`;
# если cron простоял дольше суток после урока, автозавершение, отработав
# первым, перевело бы урок в `completed` и неотправленное напоминание
# потерялось бы навсегда. Поэтому напоминания идут первыми: на первом же
# прогоне после простоя урок ещё «Запланирован», напоминание уходит, а
# автозавершение закрывает урок следом. Незавершённую доставку (сбой
# канала) задание добирает и по закрытому уроку — в режиме повтора, без
# новых захватов, — поэтому автозавершение не «съедает» и её.
TASKS: list[tuple[str, TaskCallable]] = [
    # Напоминание об уроке: за 15 минут / 1 час / 24 часа до начала —
    # репетитору во все каналы, ученику при включённом `remind_lesson`.
    # Стоит раньше автозавершения — см. пояснение выше.
    ("messenger.lesson_reminders", run_lesson_reminders),
    ("lesson.auto_complete", auto_complete_finished_lessons),
    ("messenger.daily_digest", run_daily_digests),
    ("messenger.birthday_digest", notify_birthday_digest),
    # Страховка интеграции с Google: сверка создаёт пропущенные события,
    # правит изменившиеся и удаляет осиротевшие (design D12). Ручной путь
    # синхронизирует сразу, задание догоняет то, что не прошло из-за сети.
    ("gcalendar.reconcile", reconcile_all),
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
