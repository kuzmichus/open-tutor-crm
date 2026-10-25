"""Разовые задания по расписанию: точка входа cron.

Запускается внешним планировщиком раз в минуту:

    * * * * * cd /path/to/open-tutor-crm && uv run python cron.py

Список заданий — `TASKS` в `app/common/services/cron.py`; логика заданий
живёт в доменных сервисах (например, автозавершение не отмеченных уроков —
`app/lesson/services/auto_complete.py`). Каждое задание выполняется в своей
транзакции, падение одного не мешает остальным; код возврата 1 сигнализирует
планировщику о падении.
"""

import logging
import sys

from app.common.services.cron import run_tasks

# Лог в stderr: планировщик (cron/sistemd timer) собирает его вместе с
# кодом возврата — этого достаточно для диагностики минутной задачи.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


if __name__ == "__main__":
    sys.exit(run_tasks())
