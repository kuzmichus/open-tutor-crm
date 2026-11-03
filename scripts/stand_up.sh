#!/usr/bin/env bash
# Запуск тестового стенда Open Tutor CRM для TaskDesk.
#
# Схему создаёт Alembic (приложение таблиц само не создаёт), поэтому перед
# стартом выполняется `alembic upgrade head` на выделенной SQLite-базе.
# Порт берётся из `$PORT` (его передаёт TaskDesk по контракту
# `.taskdesk/stand.toml`, `port_env`).
set -euo pipefail

PORT="${PORT:-8000}"

# База стенда — во временном каталоге: рабочее дерево не засоряется.
DB_DIR="$(mktemp -d)"
export DATABASE_URL="sqlite:///${DB_DIR}/stand.db"

# Проверка стенда запускается из публичного health-эндпоинта.
ALEMBIC_LOG="${DB_DIR}/alembic.log"
uv run alembic upgrade head > "${ALEMBIC_LOG}" 2>&1

exec uv run uvicorn main:app --host 0.0.0.0 --port "${PORT}"
