#!/usr/bin/env bash
# Старт тестового стенда Open Tutor CRM для TaskDesk.
#
# TaskDesk передаёт порт в переменной PORT (см. .taskdesk/stand.toml).
# Зависимости ставятся из uv.lock, схема базы — только миграциями Alembic:
# приложение само таблиц не создаёт и без `alembic upgrade head` упадёт
# на первом запросе с «no such table».
set -euo pipefail

cd "$(dirname "$0")/.."

: "${PORT:?TaskDesk должен передать порт в переменной PORT}"

# База по умолчанию — SQLite в корне чекаута (tutor.db исключён из git).
export DATABASE_URL="${DATABASE_URL:-sqlite:///./tutor.db}"

# Ровно версии из uv.lock, без dev-зависимостей: стенду нужны только
# рантайм-пакеты. Повторный запуск идёт из кэша uv.
uv sync --frozen --no-dev

# Схема: доводим базу до head (идемпотентно, в том числе для чистой базы).
uv run --no-sync alembic upgrade head

# --no-sync: окружение уже синхронизировано выше, не пересобирать его.
exec uv run --no-sync uvicorn main:app --host 0.0.0.0 --port "$PORT"
