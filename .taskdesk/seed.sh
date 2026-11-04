#!/usr/bin/env bash
# Наполнение тестового стенда Open Tutor CRM данными (контракт stands/seed).
#
# TaskDesk запускает скрипт до stand-up.sh и передаёт выбранный пресет
# в переменной TD_SEED_PRESET (пустая строка — «— без пресета —», это demo).
# База ещё пустая: схему поднимаем миграциями Alembic сами, как это делает
# stand-up.sh. Последняя непустая строка stdout — JSON с учётными данными,
# TaskDesk показывает её в заметке на карточке running.
set -euo pipefail

cd "$(dirname "$0")/.."

# База по умолчанию — SQLite в корне чекаута, как в [stand.env] stand.toml.
export DATABASE_URL="${DATABASE_URL:-sqlite:///./tutor.db}"

# Ровно версии из uv.lock, без dev-зависимостей; повторный запуск из кэша uv.
uv sync --frozen --no-dev

# Схема: доводим базу до head (идемпотентно, в том числе для чистой базы).
uv run --no-sync alembic upgrade head

# Пресет minimal — только карточка репетитора; всё остальное (включая пустой
# выбор «— без пресета —») — полный демо-учебный год существующим скриптом.
case "${TD_SEED_PRESET:-}" in
  minimal)
    uv run --no-sync python scripts/seed_minimal.py
    ;;
  *)
    uv run --no-sync python scripts/seed_demo.py
    ;;
esac

# Контракт кред (stands/seed): последняя непустая строка stdout — JSON.
# Значения дублируют константы TUTOR_EMAIL/TUTOR_PASSWORD из
# scripts/seed_demo.py — осознанно: парсить их в bash из питон-скрипта
# хрупче одной строки printf.
printf '{"login": "demo@example.com", "password": "12345678"}\n'
